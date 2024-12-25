import boto3
from datetime import datetime
import json
import logging
from botocore.exceptions import ClientError
import os

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def call_bedrock_inference(model_id,
                          system_prompts,
                          input_text, temperature, top_p, top_k, max_tokens):
    """
    Sends messages to a model.
    Args:
        bedrock_client: The Boto3 Bedrock runtime client.
        model_id (str): The model ID to use.
        system_prompts (JSON) : The system prompts for the model to use.
        messages (JSON) : The messages to send to the model.

    Returns:
        response (JSON): The conversation that the model generated.

    """

    logger.info("Generating message with model %s", model_id)
    
    bedrock_client = boto3.client(service_name='bedrock-runtime')

    # Base inference parameters to use.
    inference_config = {"temperature": temperature, "topP": top_p, "maxTokens": max_tokens}
    
    additional_params = {}
    # llama model not support top_k parameter
    if "llama" not in model_id.lower():
        additional_params = {"additionalModelRequestFields": {"top_k": top_k}}
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

    system = [{'text':system_prompts}]

    # Send the message.
    response = bedrock_client.converse(
        modelId=model_id,
        messages=messages,
        system=system,
        inferenceConfig=inference_config
    )

    # Log token usage.
    token_usage = response['usage']
    logger.info("Input tokens: %s", token_usage['inputTokens'])
    logger.info("Output tokens: %s", token_usage['outputTokens'])
    logger.info("Total tokens: %s", token_usage['totalTokens'])
    logger.info("Stop reason: %s", response['stopReason'])

    return response['output']['message']['content'][0]['text']

def call_sagemaker_inference(model_id,
                          system_prompts,
                          input_text, temperature, top_p, top_k, max_tokens):
    logger.info("Generating message with model %s", model_id)
    
    smr_client = boto3.client("sagemaker-runtime")
    
    prompt = "# system_prompt  \n" + system_prompts + "\n===============\n # user_input  \n" + input_text

    content = [{"type": "text", "text": prompt}]
    
    inputs = {
        "messages": [
            {
                "role": "user",
                "content": content
            }
        ],
        "max_tokens": max_tokens,
        "temperature": temperature, 
        "top_k": top_k
      }
    response = smr_client.invoke_endpoint(
        EndpointName=model_id,
        Body=json.dumps(inputs),
    )
    
    
    return json.loads(response["Body"].read().decode('utf-8'))["choices"][0]["message"]["content"]
    
    