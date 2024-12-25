import requests
import json
import base64
import os
from pathlib import Path
from typing import Dict, List, Optional, Union, Any, BinaryIO

class BRClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = os.environ.get('BRC_ENDPOINT')
        
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def chat_completion(
        self,
        model_id: str,
        system_prompts: str,
        input_text: str,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        top_p: float = 1.0,
        top_k: int = 50,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        stop: Optional[Union[str, List[str]]] = None
    ) -> str:
        """
        Create a chat completion
        
        Args:
            model_id: Model ID to use
            system_prompts: System prompt
            input_text: Input text prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            top_k: Top-k sampling parameter
            frequency_penalty: Frequency penalty parameter  
            presence_penalty: Presence penalty parameter
            stop: Stop sequence(s)
            
        Returns:
            Dict: API response
        """
        url = f"{self.base_url}/chat/completions"
        
        messages = input_text

        if system_prompts:
            messages.insert(0, {
                "role": "system",
                "content": system_prompts
            })

        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
        }
        
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if stop is not None:
            payload["stop"] = stop

        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"API request failed: {str(e)}")
    
    def prepare_image_content(self, input_image_paths: Optional[Union[str, List[str]]] = None, 
                            input_images: Optional[List[bytes]] = None) -> List[dict]:
        """
        Prepare image content for multimodal messages in OpenAI format
        
        Args:
            input_image_paths: Single path or list of paths to image files 
            input_images: List of image bytes
            
        Returns:
            List of content items in OpenAI format
        """
        content = []
        content_images = []

        # Process images from paths
        if input_image_paths is not None:
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

        # Convert image bytes to base64 and format content
        for img in content_images:
            base64_image = base64.b64encode(img).decode('utf-8')
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            })
                
        return content


    def chat_completion_with_images(
        self,
        input_text: str,
        system_prompt: str = "",
        model_id: str = "claude-3-haiku",
        temperature: float = 1.0,
        top_p: float = 1.0,
        top_k: int = 50,
        max_tokens: int = 300,
        input_image_paths: Optional[Union[str, List[str]]] = None,
        input_images: Optional[List[bytes]] = None,
    ) -> str:
        """
        Create a chat completion with image analysis support using OpenAI format
        
        Args:
            input_text: Input text prompt
            system_prompt: System prompt
            model_id: Model ID to use
            temperature: Sampling temperature
            top_p: Top-p sampling parameter
            top_k: Top-k sampling parameter 
            max_tokens: Maximum tokens to generate
            input_image_paths: Path(s) to image file(s)
            input_images: List of image bytes
            
        Returns:
            str: Model response
        """
        url = f"{self.base_url}/chat/completions"
        
        # Prepare content with images
        content = []
        
        # Add text part
        content.append({
            "type": "text", 
            "text": input_text
        })
        
        # Add image content
        content.extend(self.prepare_image_content(input_image_paths, input_images))
        
        messages = [{
            "role": "user",
            "content": content
        }]

        if system_prompt:
            messages.insert(0, {
                "role": "system",
                "content": system_prompt
            })

        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "top_k": top_k
        }

        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            raise Exception(f"API request failed: {str(e)}")

    def process_chat_with_functions(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        system: str = '',
        toolConfig: Dict[str, Any] = None
    ) -> Dict:
        """
        Process chat request with function/tool calling capability
        
        Args:
            model_id (str): The ID of the model to use
            input_messages (List[Dict[str, str]]): List of messages to send
            system (str): System prompt (default: '')
            toolConfig (Dict[str, Any]): Configuration for tools including tools list and tool choice
            
        Returns:
            Dict: API response
        """
        url = f"{self.base_url}/chat/completions"
        
        if system:
            messages.insert(0, {
                "role": "system",
                "content": system
            })
        
        payload = {
            "model": model_id,
            "messages": messages
        }

        # Add tools configuration if provided
        if toolConfig and isinstance(toolConfig, dict):
            if "tools" in toolConfig:
                payload["tools"] = toolConfig["tools"]
            if "toolChoice" in toolConfig:
                payload["tool_choice"] = toolConfig["toolChoice"]

        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"API request failed: {str(e)}")