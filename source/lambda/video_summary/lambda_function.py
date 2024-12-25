import boto3
from datetime import datetime
import json
import logging
from utils.dynamodb_utils import query_dynamodb, create_xml
from utils.inference_utils import call_bedrock_inference, call_sagemaker_inference
from utils.brconnector_utils import BRClient
from botocore.exceptions import ClientError
import os

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
    
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
    
def call_inference(**kwargs):
    if kwargs['model_id'].lower().startswith("sagemaker"):
        return call_sagemaker_inference(**kwargs)
    elif os.environ.get('BRC_ENABLE') == 'Y':
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
        brc_response = brclient.chat_completion(**kwargs)
        return brc_response
    else:
        return call_bedrock_inference(**kwargs)

def lambda_handler(event, context):

    logger.info('video summary: {}'.format(event))

    model_id = event.get('model_id', "anthropic.claude-3-haiku-20240307-v1:0")

    temperature = event.get('temperature', 0.5)
    top_p = event.get('top_p', 1.0)
    top_k = event.get('top_k', 250)
    max_tokens = event.get('max_tokens', 2048)

    user_id = event.get('user_id', 'id_placeholder')
    task_id = event.get('task_id', 'task_placeholder')
    connection_id = event.get('connection_id', 'connection_placeholder')
    postprocess_prompt = "pls summary the video content"

    input_frame_result = query_dynamodb(user_id, task_id)
    query_result = create_xml(input_frame_result)

    record = query_result
    prompt_prefix = """Below is video analytics event results.\n"""
    postprocess_prompt = '\n<task>\n' + postprocess_prompt + '\n</task>' 
    
    input_text = prompt_prefix + record + postprocess_prompt

    system_prompts = "You're an assisstant for video content summary, pls summarize the images description from videos frames in brief sentences."
    result = call_inference(model_id=model_id, 
        system_prompts=system_prompts, 
        input_text=input_text, 
        temperature=temperature, 
        top_p=top_p, 
        top_k=top_k, 
        max_tokens=max_tokens)
        
    output_message = result
    print(output_message)
    
    notify_request = {
        "payload": {
            "summary_result": output_message,
            "task_id": task_id
        },
        "connection_id": connection_id
    }

    # 调用NotifyLambda
    invoke_notify_lambda(os.environ['NotifyLambda'], notify_request)

    return {
        'statusCode': 200,
        'body': json.dumps({'summary_result': output_message}, ensure_ascii=False)
    }