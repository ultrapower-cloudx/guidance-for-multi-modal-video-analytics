import json
import requests
from datetime import datetime
import os
import boto3
import uuid

def brconnect_with_tools(model_id, messages, system, tool_config):
    url = f"{os.environ.get('BRC_ENDPOINT')}/chat/completions"

    secret_client = boto3.client('secretsmanager')
    try:
        get_secret_value_response = secret_client.get_secret_value(
            SecretId='brconnector-apikey'
        )
    except Exception as e:
        print(f"error in create opensearch client, exception={e}")
        raise e

    brc_api_key = get_secret_value_response['SecretString']

    headers = {
        "Authorization": f"Bearer {brc_api_key}",
        "Content-Type": "application/json"
    }
    
    formatted_messages = format_messages_for_openai(messages, system)
    tools = convert_tools_to_functions(tool_config)
    
    # 修改 payload 结构
    payload = {
        "model": model_id,
        "messages": formatted_messages,
        "temperature": 1.0,
        "top_p": 1.0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "tools": tools,
        "tool_choice": "auto"
    }
    
    print("Debug - payload:", payload)
    response = requests.post(url, headers=headers, json=payload)
    response_data = response.json()
    return output_format(response_data)

def format_messages_for_openai(messages, system):
    """
    Convert the custom message format to OpenAI's format
    """
    formatted_messages = [{"role": "system", "content": system}]
    
    for message in messages:
        if message["role"] == "user":
            # Handle regular text content
            if isinstance(message["content"], list):
                content = next((item["text"] for item in message["content"] 
                              if "text" in item), "")
                if content:
                    formatted_messages.append({
                        "role": "user",
                        "content": content
                    })
                
                # Handle tool results
                tool_result = next((item["toolResult"] for item in message["content"] 
                                  if "toolResult" in item), None)
                if tool_result:
                    formatted_messages.append({
                        "role": "function",
                        "name": tool_result["toolUseId"].split("_")[0],
                        "content": tool_result["content"][0]["text"]
                    })
        
        elif message["role"] == "assistant":
            content = message.get("content", [])
            text_content = next((item["text"] for item in content 
                               if "text" in item), "")
            tool_use = next((item["toolUse"] for item in content 
                           if "toolUse" in item), None)
            
            if tool_use:
                formatted_messages.append({
                    "role": "assistant",
                    "content": None,
                    "function_call": {
                        "name": tool_use["name"],
                        "arguments": json.dumps(tool_use["input"])
                    }
                })
            elif text_content:
                formatted_messages.append({
                    "role": "assistant",
                    "content": text_content
                })
    
    return formatted_messages

def convert_tools_to_functions(tool_config):
    """
    Convert tool configurations to OpenAI function format
    """
    tools = []
    for tool in tool_config['tools']:
        tool_spec = tool['toolSpec']
        function_def = {
            "type": "function",
            "function": {
                "name": tool_spec['name'],
                "description": tool_spec['description'],
                "parameters": tool_spec['inputSchema']['json']
            }
        }
        tools.append(function_def)
    return tools

def output_format(current_output):
    """
    将当前格式转换为期望格式
    
    Args:
        current_output (dict): 当前输出格式的字典
        
    Returns:
        dict: 转换后的期望格式字典
    """
    try:
        # 从当前输出中获取参数
        tool_calls = current_output["choices"][0]["message"]["tool_calls"][0]
        function_name = tool_calls["function"]["name"]
        arguments = tool_calls["function"]["arguments"]
        
        # 生成toolUseId
        tool_use_id = "tooluse_mock"
        
        # 构建新的输出格式
        new_output = {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": tool_use_id,
                            "name": function_name,
                            "input": arguments
                        }
                    }
                ]
            }
        }
        
        return new_output
        
    except Exception as e:
        print(f"Format conversion error: {str(e)}")
        return None

