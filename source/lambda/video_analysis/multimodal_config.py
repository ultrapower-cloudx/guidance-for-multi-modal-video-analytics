import boto3
import os
import tempfile
import json
import logging
from pathlib import Path
import base64
import time
from botocore.exceptions import ClientError

bedrock_runtime = boto3.client(service_name='bedrock-runtime')

def run_multi_modal_prompt(bedrock_runtime, model_id, messages, system_prompt, inferenceConfig, additionalModelFields):
        """
        Invokes a model with a multimodal prompt.
            bedrock_runtime: The Amazon Bedrock boto3 client.
            model_id (str): The model ID to use.
            messages (JSON) : The messages to send to the model.
        """

        t0 = time.time()
        additional_params = {}
        # llama model not support top_k parameter
        if "llama" not in model_id.lower():
            additional_params = {"additionalModelRequestFields": additionalModelFields} 
            
        response = bedrock_runtime.converse(modelId=model_id, messages=messages, system=system_prompt, inferenceConfig=inferenceConfig, **additional_params)
        # response_body = response["output"]["message"]["content"][0]["text"]
        
        t1 = time.time()
        print("Invoke Cost: ",t1-t0)

        return response
        
def call_claude3_img(input_text, system_prompt, model_id, temperature, top_p, top_k, max_tokens, input_image_paths=None, input_images=None):
    """
    input_text: 输入的prompt
    input_image_paths & input_images: 图像的输入为list，输入为一组图像地址input_image_paths或者base64编码后的图像input_images，优先input_image_paths
    """

    try:
        
        if input_image_paths is not None:
            content_images = []
            if Path(input_image_paths).is_file():
                print("file path is ", input_image_paths)
                with open(input_image_paths, "rb") as image_file:
                    content_images.append(image_file.read())
            elif Path(input_image_paths).is_dir():
                print("dir path is ", input_image_paths)
                for input_image_path in Path(input_image_paths).glob('*.jpg'):
                    with open(input_image_path, "rb") as image_file:
                        content_images.append(image_file.read())
        else:
            print('image')
            content_images = input_images
        
        content = [
            [
                {
                    "text": f"Image {i}"
                },
                {
                    "image":
                    {
                        "format": "jpeg", 
                        "source": {
                        "bytes": content_image
                        }
                    }
                }
            ]
            for i, content_image in enumerate(content_images)
        ]
        content = [item for sublist in content for item in sublist]   
            
        # content text
        content.append({"text": input_text})
        message = {"role": "user",
                    "content": content}
        
        messages = [message]

        system = [{'text':system_prompt}]

        inferenceConfig = {
        "maxTokens": max_tokens,
        "temperature": temperature, 
        "topP": top_p
        }

        additionalModelFields = {"top_k": top_k}

        response = run_multi_modal_prompt(
            bedrock_runtime, model_id, messages, system, inferenceConfig, additionalModelFields)
        # print(response, type(response))
        # print(json.dumps(response, indent=4))
        return response["output"]["message"]["content"][0]["text"]

    except (ClientError, Exception) as e:
        print(f"ERROR: Can't invoke '{model_id}'. Reason: {e}")
        exit(1)
        
def run_inference(endpoint_name, inputs):
    smr_client = boto3.client("sagemaker-runtime")
    response = smr_client.invoke_endpoint(
        EndpointName=endpoint_name, Body=json.dumps(inputs)
    )
    return response["Body"].read().decode('utf-8')

def call_sagemaker_llava(input_text, system_prompt, model_id, temperature, top_p, top_k, max_tokens, input_image_paths=None, input_images=None):
    
    if input_image_paths is not None:
        content_images = []
        if Path(input_image_paths).is_file():
            print("file path is ", input_image_paths)
            with open(input_image_paths, "rb") as image_file:
                encode_image = base64.b64encode(image_file.read()).decode('utf-8')
                content_images.append(encode_image)
        elif Path(input_image_paths).is_dir():
            print("dir path is ", input_image_paths)
            for input_image_path in Path(input_image_paths).glob('*.jpg'):
                with open(input_image_path, "rb") as image_file:
                    encode_image = base64.b64encode(image_file.read()).decode('utf-8')
                    content_images.append(encode_image)
    else:
        print('image')
        content_images = input_images
    
    print(len(content_images))
    
    prompt = "# system_prompt  \n" + system_prompt + "\n===============\n # user_input  \n" + input_text
    
    content = [{"type": "text", "text": prompt}]
    
    content += [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}} for base64_image in content_images]

    # print(content)

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

    response = run_inference(model_id, inputs)
   
    try:
        outputs = json.loads(response)["choices"][0]["message"]["content"]
        return outputs
    except:
        return response