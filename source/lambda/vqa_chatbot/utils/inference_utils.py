import boto3
import logging
import json
import os
from botocore.exceptions import ClientError
from utils.brconnector_utils import BRClient

bedrock_runtime = boto3.client(service_name='bedrock-runtime')

logger = logging.getLogger()

def invoke_notify_lambda(notify_lambda_name, notify_request):
    """
    调用NotifyLambda函数
    :param notify_lambda_name: NotifyLambda函数名称
    :param notify_request: 请求参数
    """
    try:
        lambda_client = boto3.client('lambda')
        lambda_client.invoke(
            FunctionName=notify_lambda_name,
            InvocationType='Event',
            Payload=bytes(json.dumps(notify_request), encoding='utf-8')
        )
    except Exception as e:
        logger.error(f'Error occurred while invoking Lambda function: {e}')
        raise e

def bedrock_conversation(bedrock_client,
                    model_id,
                    messages,
                    system_prompts,
                    inference_config,
                    ):
    """
    Sends messages to a model and streams the response.
    Args:
        bedrock_client: The Boto3 Bedrock runtime client.
        model_id (str): The model ID to use.
        messages (JSON) : The messages to send.
        system_prompts (JSON) : The system prompts to send.
        inference_config (JSON) : The inference configuration to use.
        additional_model_fields (JSON) : Additional model fields to use.

    Returns:
        Nothing.

    """

    logger.info("Streaming messages with model %s", model_id)

    response = bedrock_client.converse_stream(
        modelId=model_id,
        messages=messages,
        system=system_prompts,
        inferenceConfig=inference_config,
    )

    stream = response.get('stream')
    answer = ""
    input_tokens = 0
    output_tokens = 0
    
    if stream:
        for event in stream:

            # if 'messageStart' in event:
            #     print(f"\nRole: {event['messageStart']['role']}")

            if 'contentBlockDelta' in event:
                text = event['contentBlockDelta']['delta']['text']
                print(text, end="")
                
            #     notify_request = {
            #     "payload": {
            #         "analysis_result": text
            #     },
            #     "connection_id": connection_id
            # }
            #     # 调用NotifyLambda
            #     invoke_notify_lambda(os.environ['NotifyLambda'], notify_request)
                answer += str(text)

            # if 'messageStop' in event:
            #     print(f"\nStop reason: {event['messageStop']['stopReason']}")

            if 'metadata' in event:
                metadata = event['metadata']
                if 'usage' in metadata:
                    print("\nToken usage")
                    input_tokens = metadata['usage']['inputTokens']
                    output_tokens = metadata['usage']['outputTokens']
                    print("Input tokens: ", input_tokens)
                    print("Output tokens: ", output_tokens)
                if 'metrics' in event['metadata']:
                    print(
                        f"Latency: {metadata['metrics']['latencyMs']} ms")
                    
    return answer, input_tokens, output_tokens


def call_bedrock_inference(chat_history,system_message, prompt,model_id):

    content=[]
    content.append({"text": prompt})
    chat_history.append({"role": "user",
            "content": content})

    system = [{'text':system_message}]

    inferenceConfig = {
    "maxTokens": 2048,
    "temperature": 0.5, 
    "topP": 1
    }


    # additional_model_fields = {"top_k": 200}

    answer,input_tokens,output_tokens=bedrock_conversation(bedrock_runtime, model_id, chat_history,
                        system, inferenceConfig)

    return answer, input_tokens, output_tokens

def call_sagemaker_inference(chat_history,system_message, prompt,model_id):

    smr_client = boto3.client("sagemaker-runtime")

    content = "# system_prompt  \n" + system_message + "\n===============\n # user_input  \n" + prompt

    chat_history.append({"role": "user",
        "content": content})
        
    print(chat_history)

    inputs = {
        "messages": chat_history,
        "max_tokens": 2048,
        "temperature": 0.5, 
        "top_k": 200
      }
      
    response = smr_client.invoke_endpoint(
        EndpointName=model_id,
        Body=json.dumps(inputs),
    )
    
    response_json = json.loads(response["Body"].read().decode('utf-8'))
    
    # print(response_json)

    answer = response_json["choices"][0]["message"]["content"]
    input_tokens = response_json['usage']['prompt_tokens']
    output_tokens = response_json['usage']['completion_tokens']
    print("sagemaker done")

    return answer, input_tokens, output_tokens

def call_brclient_inference(chat_history,system_message, prompt,model_id):

    chat_history.append({"role": "user",
            "content": prompt})

    system = system_message

    inputs = {
        "messages": chat_history,
        "max_tokens": 2048,
        "temperature": 0.5, 
        "top_k": 200
      }


    secret_client = boto3.client('secretsmanager')
    try:
        get_secret_value_response = secret_client.get_secret_value(
            SecretId='brconnector-apikey'
        )
    except Exception as e:
        print(f"error in create opensearch client, exception={e}")
        raise e
    brc_api_key = get_secret_value_response['SecretString']
    
    brclient = BRClient(api_key=brc_api_key)  
    response = brclient.chat_completion(
        model_id=model_id,
        system_prompts=system,
        input_text=chat_history
        )
    
    answer = response["choices"][0]["message"]["content"]
    input_tokens = response["usage"]["prompt_tokens"]
    output_tokens = response["usage"]["completion_tokens"]

    return answer, input_tokens, output_tokens

def call_inference(**kwargs):
    if kwargs['model_id'].lower().startswith("sagemaker"):
        return call_sagemaker_inference(**kwargs)
    elif os.environ.get('BRC_ENABLE') == 'Y':
        brc_response = call_brclient_inference(**kwargs)
        return brc_response
    else:
        return call_bedrock_inference(**kwargs)

def _invoke_with_retries(chat_history,system_message, prompt,model_id):
    max_retries = 5
    backoff_base = 2
    max_backoff = 3  # Maximum backoff time in seconds
    retries = 0

    while True:
        try:
            response,input_tokens,output_tokens= call_inference(chat_history=chat_history,system_message=system_message, prompt=prompt,model_id=model_id)
            return response,input_tokens,output_tokens
        except ClientError as e:
            if e.response['Error']['Code'] == 'ThrottlingException':
                if retries < max_retries:
                    # Throttling, exponential backoff
                    sleep_time = min(max_backoff, backoff_base ** retries + random.uniform(0, 1))
                    time.sleep(sleep_time)
                    retries += 1
                else:
                    raise e
            elif e.response['Error']['Code'] == 'ModelStreamErrorException':
                if retries < max_retries:
                    # Throttling, exponential backoff
                    sleep_time = min(max_backoff, backoff_base ** retries + random.uniform(0, 1))
                    time.sleep(sleep_time)
                    retries += 1
                else:
                    raise e
            elif e.response['Error']['Code'] == 'EventStreamError':
                if retries < max_retries:
                    # Throttling, exponential backoff
                    sleep_time = min(max_backoff, backoff_base ** retries + random.uniform(0, 1))
                    time.sleep(sleep_time)
                    retries += 1
                else:
                    raise e
            else:
                # Some other API error, rethrow
                raise