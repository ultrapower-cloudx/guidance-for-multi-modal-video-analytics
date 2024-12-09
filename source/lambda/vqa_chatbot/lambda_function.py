import json
import boto3
import xml.etree.ElementTree as ET
import time
import logging
import os
from botocore.exceptions import ClientError
from utils.dynamodb_utils import query_dynamodb, put_db, get_chat_history_db, create_xml
from utils.inference_utils import _invoke_with_retries

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CHAT_HISTORY_LENGTH = 5

dynamodb = boto3.resource('dynamodb')

query_table_name = os.environ["RESULT_DYNAMODB"]
query_table = dynamodb.Table(query_table_name)

chat_table_name = os.environ["HISTORY_DYNAMODB"]
chat_table = dynamodb.Table(chat_table_name)

def conversation_chat_(question, model_id, user_id, task_id):

    num_retries=0
    current_chat=[]
   
    # Retrieve past chat history from Dynamodb
    chat_histories = dynamodb.Table(chat_table_name).get_item(Key={"UserId": user_id, "SessionId":task_id})
    if "Item" in chat_histories:            
        current_chat,chat_hist=get_chat_history_db(chat_histories, CHAT_HISTORY_LENGTH, model_id)
    else:
        chat_hist=[]
    
    doc="I have provided documents"
    input_frame_result = query_dynamodb(user_id, task_id)
    query_result = create_xml(input_frame_result)
    doc+= query_result
    # print(doc)
    
    chat_template = 'you are an assistant and will analysis a serious image description from one video'
    response,input_tokens,output_tokens=_invoke_with_retries(current_chat, chat_template, doc+question, model_id)
    chat_history={"user":question,
    "assistant":response,
    "modelID":model_id,
    "time":str(time.time()),
    "input_token":round(input_tokens) ,
    "output_token":round(output_tokens)}         
                 
    #store convsation memory in DynamoDB table
    put_db(chat_history, user_id, task_id)

    return response

def lambda_handler(event, context):
    try:
        logger.info('vqa_chatbot: {}'.format(event))
        
        user_id = event['user_id']
        task_id = event['task_id']
        question = event['vqa_prompt']
        
        follow_front = os.environ.get('FOLLOW_FRONT')
        model_name = os.environ.get('MODEL_NAME')
        
        if follow_front is None and model_name is None:
            model_id = event['model_id']
        elif follow_front and follow_front.upper() == 'Y':
            model_id = event['model_id']
        else:
            model_id = model_name or event['model_id']
        
        response = conversation_chat_(question, model_id, user_id, task_id)
        return {
            'statusCode': 200,
            'action': 'vqa_chatbot',
            'body': json.dumps({'vqa_result':response}, ensure_ascii=False)
        }
    except Exception as e:
        logger.error(f"Error: {e}")
        return {
            'statusCode': 500,
            'body': str(e)
        }
