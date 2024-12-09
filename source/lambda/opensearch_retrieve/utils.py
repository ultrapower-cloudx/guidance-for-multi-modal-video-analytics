import requests
import boto3
import json
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests.auth import HTTPBasicAuth
from pathlib import Path
import cohere_aws
import base64
import os
from botocore.exceptions import ClientError
from urllib.parse import urlparse

# Define bedrock client
bedrock_client = boto3.client("bedrock-runtime")

# Bedrock models
# Select Amazon titan-embed-image-v1 as Embedding model for multimodal indexing
multimodal_embed_model = f'amazon.titan-embed-image-v1'

"""
Function to generate Embeddings from image or text
"""

def get_titan_multimodal_embedding(
    image_path:str=None,  # maximum 2048 x 2048 pixels
    description:str=None, # English only and max input tokens 128
    dimension:int=1024,   # 1,024 (default), 384, 256
    model_id:str=multimodal_embed_model
):
    payload_body = {}
    embedding_config = {
        "embeddingConfig": { 
             "outputEmbeddingLength": dimension
         }
    }
    # You can specify either text or image or both
    if image_path:
        if image_path.startswith('s3'):
            s3 = boto3.client('s3')
            bucket_name, key = image_path.replace("s3://", "").split("/", 1)
            obj = s3.get_object(Bucket=bucket_name, Key=key)
            # Read the object's body
            body = obj['Body'].read()
            # Encode the body in base64
            base64_image = base64.b64encode(body).decode('utf-8')
            payload_body["inputImage"] = base64_image
        else:   
            with open(image_path, "rb") as image_file:
                input_image = base64.b64encode(image_file.read()).decode('utf8')
            payload_body["inputImage"] = input_image
    if description:
        payload_body["inputText"] = description

    assert payload_body, "please provide either an image and/or a text description"
    # print("\n".join(payload_body.keys()))

    response = bedrock_client.invoke_model(
        body=json.dumps({**payload_body, **embedding_config}), 
        modelId=model_id,
        accept="application/json", 
        contentType="application/json"
    )

    return json.loads(response.get("body").read())




def setup_opensearch_client():
    # headers = {"Content-Type": "application/json"}
    host = os.environ["OPENSEARCH_ENDPOINT"] #<opensearch domain endpoint without 'https://'> #example: "opensearch-domain-endpoint.us-east-1.es.amazonaws.com"
    # service = 'es'
    # region = "us-east-1"

    # Use OpenSearch master credentials that you created while creating the OpenSearch domain
    secret_client = boto3.client('secretsmanager')
    try:
        get_secret_value_response = secret_client.get_secret_value(
            SecretId='opensearch-master-user'
        )
    except Exception as e:
        print(f"error in create opensearch client, exception={e}")
        raise e

    # 解码密钥值
    secret_string = get_secret_value_response['SecretString']
    secret_dict = json.loads(secret_string)
    awsauth = HTTPBasicAuth(secret_dict["username"],secret_dict["password"])


    #Initialise OpenSearch-py client
    aos_client = OpenSearch(
        hosts = [{'host': host, 'port': 443}],
        http_auth = awsauth,
        use_ssl = True,
        connection_class = RequestsHttpConnection
    )
    
    return aos_client

def get_presigned_url_from_uri(uri):
    try:
        parsed_uri = urlparse(uri)
        
        if parsed_uri.scheme != 's3':
            raise ValueError("Invalid URI scheme. Expected 's3://'")
        
        bucket_name = parsed_uri.netloc
        key = parsed_uri.path.lstrip('/') 
        
        expiration = 600

        s3 = boto3.client('s3')

        url = s3.generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': bucket_name,
                'Key': key,
                'ResponseContentType': 'image/jpeg'
            },
            ExpiresIn=expiration
        )
        print(f"URL: {url}")
        return url
        
    except ClientError as e:
        print(f"Error: {e.response['Error']['Message']}")
    except ValueError as e:
        print(f"Error: {str(e)}")

def rerank_index(results, keyword):
    co = cohere_aws.Client()
    co.connect_to_endpoint(endpoint_name="cohere-rerank-multilingual")

    wait_rerank_list = [item['description'] for item in results]
    rerank_results = co.rerank(query=keyword, documents=wait_rerank_list).results
    new_index = []
    for rerank_result in rerank_results:
        new_index.append(rerank_result.index)
        
    return new_index
    
def call_bedrock_inference(model_id,input_text):
    
    prompt_content = '''
    Here's the English translation of the prompt:

    You are a keyword extraction assistant. Your purpose is to extract key search terms from user input to be submitted to a search engine. Here are the requirements:

    <instruction>
    1. Extract only one object
    2. The object can include modifiers and adjectives
    3. The output should contain only the extracted object, without any additional content
    4. Maintain the original language. If the input is in Chinese, output in Chinese; if the input is in English, output in English."
    </instruction>

    Below are examples of expected outputs for different inputs:

    <example>
    input: Please return all shots of babies crying
    output: crying babies

    input: all images include tigers staying under tree
    output: tigers staying under tree
    </example>
    '''
    system_prompts = [{"text": prompt_content}]
    
    # Base inference parameters to use.
    # inference_config = {"temperature": temperature, "topP": top_p, "maxTokens": max_tokens}
    
    # additional_params = {}
    # llama model not support top_k parameter
    # if "llama" not in model_id.lower():
    #     additional_params = {"additionalModelRequestFields": {"top_k": top_k}}
    messages = []
    messages.append(
        {
            "role": "user",
            "content": [
                {
                    "text": input_text
                }
            ]
        }
    )

    # Send the message.
    response = bedrock_client.converse(
        modelId=model_id,
        messages=messages,
        system=system_prompts,
    )
    
    return response['output']['message']['content'][0]['text']

def call_sagemaker_inference(model_id,input_text):
    
    smr_client = boto3.client("sagemaker-runtime")
    
    prompt_content = '''
    Here's the English translation of the prompt:

    You are a keyword extraction assistant. Your purpose is to extract key search terms from user input to be submitted to a search engine. Here are the requirements:

    <instruction>
    1. Extract only one object
    2. The object can include modifiers and adjectives
    3. The output should contain only the extracted object, without any additional content
    4. Maintain the original language. If the input is in Chinese, output in Chinese; if the input is in English, output in English."
    </instruction>

    Below are examples of expected outputs for different inputs:

    <example>
    input: Please return all shots of babies crying
    output: crying babies

    input: all images include tigers staying under tree
    output: tigers staying under tree
    </example>
    '''
    system_prompts = [{"text": prompt_content}]
    
    prompt = "# system_prompt  \n" + system_prompts[0]["text"] + "\n===============\n # user_input  \n" + input_text

    content = [{"type": "text", "text": prompt}]
    
    inputs = {
        "messages": [
            {
                "role": "user",
                "content": content
            }
        ]
      }
    response = smr_client.invoke_endpoint(
        EndpointName=model_id,
        Body=json.dumps(inputs),
    )
    
    return json.loads(response["Body"].read().decode('utf-8'))["choices"][0]["message"]["content"]

def call_inference(**kwargs):
    if kwargs['model_id'].lower().startswith("sagemaker"):
        return call_sagemaker_inference(**kwargs)
    else:
        return call_bedrock_inference(**kwargs)