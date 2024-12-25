import boto3
from datetime import datetime
import json
import logging
import os
from dynamodb_utils import query_dynamodb, create_xml
from brconnector_utils import brconnect_with_tools
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

bedrock = boto3.client(
    service_name = 'bedrock-runtime'
    )

class ToolsList:
    #Define our get_weather tool function...
    def send_notification(self, condition, message, receiver=None):
        print('in toolslist', condition, message, receiver)
        try:
            lambda_client = boto3.client('lambda')
            response = lambda_client.invoke(
                FunctionName=os.environ['TOOL_NOTIFICATION_LAMBDA'],
                InvocationType='Event',
                Payload=json.dumps(
                    {
                        "condition": condition,
                        "message": message,
                        "receiver": receiver
                    }
                    )
            )
        except Exception as e:
            logger.error(f'Error occurred while invoking Lambda function: {e}')
            raise e
        
        return json.dumps(response['Payload'].read().decode('utf-8'))
    
    def send_device_mqtt(self, level, command):
        print('in toolslist', command)
        try:
            lambda_client = boto3.client('lambda')
            response = lambda_client.invoke(
                FunctionName=os.environ['TOOL_DEVICE_LAMBDA'],
                InvocationType='Event',
                Payload=json.dumps(
                    {
                        "level":level,
                        "command": command
                    }
                    )
            )
        except Exception as e:
            logger.error(f'Error occurred while invoking Lambda function: {e}')
            raise e
        
        return json.dumps(response['Payload'].read().decode('utf-8'))
        
    def nothing(self, **kwargs):
        response = 'no match tool, do nothing'
        print(response)
        return response
    
#Define the configuration for our tool...
toolConfig = {'tools': [],
'toolChoice': {
    'auto': {},
    }
}

toolConfig['tools'].append({
        'toolSpec': {
            'name': 'send_notification',
            'description': 'send mail to receiver when meet condition.',
            'inputSchema': {
                'json': {
                    'type': 'object',
                    'properties': {
                        'condition': {
                            'type': 'string',
                            'description': 'meet what condition to do action'
                        },
                        'message': {
                            'type': 'string',
                            'description': 'what message will be sent if meet condition'
                        },
                    },
                    'required': ['condition', 'message']
                }
            }
        }
    })

toolConfig['tools'].append({
        'toolSpec': {
            'name': 'send_device_mqtt',
            'description': 'send command to control device.',
            'inputSchema': {
                'json': {
                    'type': 'object',
                    'properties': {
                        'level': {
                            'type': 'string',
                            'description': 'the emergency level, options include [alert, reminder]'
                        },
                        'command': {
                            'type': 'string',
                            'description': 'meet what condition to do action'
                        },
                    },
                    'required': ['level', 'command']
                }
            }
        }
    })
toolConfig['tools'].append({
    'toolSpec': {
        'name': 'nothing',
        'description': 'if no matched tool, do nothing',
        'inputSchema': {
            'json': {
                'type': 'object',
                'properties': {},
            }
        }
    }
})

#Function for caling the Bedrock Converse API...
def converse_with_tools(model_id, prompt, system, tool_config):
    if os.environ.get('BRC_ENABLE') == 'Y':
        response = brconnect_with_tools(model_id, prompt, system, tool_config)
    else:
        system_prompts = [{'text':system}]
        converse_response = bedrock.converse(
            modelId=model_id,
            system=system_prompts,
            messages=prompt,
            toolConfig=tool_config
        )
        response = converse_response['output']
    return response

#Function for orchestrating the conversation flow...
def converse(model_id, prompt, system, tool_config):
    #Add the initial prompt:
    messages = []
    messages.append(
        {
            "role": "user",
            "content": [
                {
                    "text": prompt
                }
            ]
        }
    )
    print(f"\n{datetime.now().strftime('%H:%M:%S')} - Initial prompt:\n{messages=}")

    #Invoke the model the first time:
    output = converse_with_tools(model_id, messages, system, tool_config)
    print('output is', output)
    print(f"\n{datetime.now().strftime('%H:%M:%S')} - Output so far:\n{output}")

    #Add the intermediate output to the prompt:
    messages.append(output['message'])

    function_calling = next((c['toolUse'] for c in output['message']['content'] if 'toolUse' in c), None)

    print('function_call is ',function_calling)

    #Check if function calling is triggered:
    if function_calling:
        #Get the tool name and arguments:
        tool_name = function_calling['name']
        tool_args = function_calling['input'] or {}
        
        #Run the tool:
        print(f"\n{datetime.now().strftime('%H:%M:%S')} - Running ({tool_name}) tool...")
        tool_response = getattr(ToolsList(), tool_name)(**tool_args) or ""
        if tool_response:
            tool_status = 'success'
        else:
            tool_status = 'error'

        #Add the tool result to the prompt:
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        'toolResult': {
                            'toolUseId':function_calling['toolUseId'],
                            'content': [
                                {
                                    "text": tool_response
                                }
                            ],
                            'status': tool_status
                        }
                    }
                ]
            }
        )
        print(f"\n{datetime.now().strftime('%H:%M:%S')} - Messages so far:\n{messages}")

        #Invoke the model one more time:
        output = converse_with_tools(model_id, messages, system, tool_config)
        print(f"\n{datetime.now().strftime('%H:%M:%S')} - Final output:\n{output}\n")
    return output

def lambda_handler(event, context):
    
    user_id = event.get('user_id', 'userid_placeholder')
    task_id = event.get('task_id', 'task_placeholder')
    postprocess_prompt = event.get('agent_prompt', 'agent_placeholder')
    
    follow_front = os.environ.get('FOLLOW_FRONT')
    model_name = os.environ.get('MODEL_NAME')
    
    if follow_front is None and model_name is None:
        model_id = event['model']
    elif follow_front and follow_front.upper() == 'Y':
        model_id = event['model']
    else:
        model_id = model_name or event['model']

    print(f'Using modelId: {model_id}')
    
    input_frame_result = query_dynamodb(user_id, task_id)
    query_result = create_xml(input_frame_result)

    record = query_result
    prompt_prefix = """Below is video analytics event results.\n"""
    postprocess_prompt = '\n<task>\n' + postprocess_prompt + '\n</task>' 
    
    final_input = prompt_prefix + record + postprocess_prompt

    prompts = [final_input]
    system = "You're provided with a tool that can send mail to receiver person or send command to device or do nothing; \
                only use the tool if required. Don't make reference to the tools in your final answer."
    result =""
    for prompt in prompts:
        response = converse(
            model_id = model_id,
            prompt = prompt,
            system = system,
            tool_config = toolConfig
    )
        result = response

    output_result = result['message']['content'][0]['text']
    return {
        'statusCode': 200,
        'action': 'configure_agent',
        'body': json.dumps({'agent_result': output_result}, ensure_ascii=False)
    }
