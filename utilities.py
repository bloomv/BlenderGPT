import bpy
import openai
import re
import os
import sys
import requests
import json


def get_api_key(context, addon_name):
    preferences = context.preferences
    addon_prefs = preferences.addons[addon_name].preferences
    return addon_prefs.api_key


def init_props():
    bpy.types.Scene.gpt4_chat_history = bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)
    bpy.types.Scene.gpt4_model = bpy.props.EnumProperty(
    name="GPT Model",
    description="Select the GPT model to use",
    items=[
        ("gemma-7b", "Gemma-7B (less powerful, free)", "Use GPT-Gemma-7B"), 
        ("gpt-4", "GPT-4 (powerful, expensive)", "Use GPT-4"),
        ("gpt-3.5-turbo", "GPT-3.5 Turbo (less powerful, cheaper)", "Use GPT-3.5 Turbo"),
    ],
    default="gpt-4",
)
    bpy.types.Scene.gpt4_chat_input = bpy.props.StringProperty(
        name="Message",
        description="Enter your message",
        default="",
    )
    bpy.types.Scene.gpt4_button_pressed = bpy.props.BoolProperty(default=False)
    bpy.types.PropertyGroup.type = bpy.props.StringProperty()
    bpy.types.PropertyGroup.content = bpy.props.StringProperty()

def clear_props():
    del bpy.types.Scene.gpt4_chat_history
    del bpy.types.Scene.gpt4_chat_input
    del bpy.types.Scene.gpt4_button_pressed

def generate_blender_code(prompt, chat_history, context, system_prompt):
    # ngc api
    if context.scene.gpt4_model == "gemma-7b":
        invoke_url = "https://api.nvcf.nvidia.com/v2/nvcf/pexec/functions/1361fa56-61d7-4a12-af32-69a3825746fa"
        fetch_url_format = "https://api.nvcf.nvidia.com/v2/nvcf/pexec/status/"

        # API_KEY_REQUIRED_IF_EXECUTING_OUTSIDE_NGC
        # The following key has been successfully generated. This is the only time your key will be displayed. 
        # This key is for API testing use only and is valid for 30 days.
        API_KEY = "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"
        headers = {
            #"Authorization": "Bearer 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",
            "Authorization": f"Bearer {API_KEY}",
            "Accept": "text/event-stream", #"application/json",
        }

        messages = [{"role": "system", "content": system_prompt}]
        for message in chat_history[-10:]:
            if message.type == "assistant":
                messages.append({"role": "assistant", "content": "```\n" + message.content + "\n```"})
            else:
                messages.append({"role": message.type.lower(), "content": message.content})

        # Add the current user message
        messages.append({"role": "user", "content": "Can you please write Blender code for me that accomplishes the following task: " + prompt + "? \n. Do not respond with anything that is not Python code. Do not provide explanations"})

        payload = {
        "messages": messages,
        "temperature": 0.2,
        "top_p": 0.7,
        "max_tokens": 1024*8,
        "seed": 42,
        "bad": None,
        "stop": None,
        "stream": True, # False
        }
        
        # re-use connections
        session = requests.Session()

        response = session.post(invoke_url, headers=headers, json=payload, stream=True)

        try:
            collected_events = []
            completion_text = ''
            # iterate through the stream of events
            for line in response.iter_lines():
            #for event in response:
                if line:
                    data = line.decode("utf-8").replace('data: ', '')
                    print(data)
                    if data != '[DONE]':
                        event = json.loads(data)
                        #if 'role' in event['choices'][0]['delta']:
                            # skip
                        #    continue
                        #if len(event['choices'][0]['delta']) == 0:
                        #    # skip
                        #    continue
                        collected_events.append(event)  # save the event response
                        event_text = event['choices'][0]['delta']['content']
                        completion_text += event_text  # append the text
                        #print(completion_text, flush=True, end='\r')
            completion_text = re.findall(r'```(.*?)```', completion_text, re.DOTALL)[0]
            completion_text = re.sub(r'^python', '', completion_text, flags=re.MULTILINE)
            return completion_text
        except IndexError:
            return None
        #except json.decoder.JSONDecodeError:
        #    completion_text = re.findall(r'```(.*?)```', completion_text, re.DOTALL)[0]
        #    completion_text = re.sub(r'^python', '', completion_text, flags=re.MULTILINE)
        #    return completion_text #None
    
    # openai api
    messages = [{"role": "system", "content": system_prompt}]
    for message in chat_history[-10:]:
        if message.type == "assistant":
            messages.append({"role": "assistant", "content": "```\n" + message.content + "\n```"})
        else:
            messages.append({"role": message.type.lower(), "content": message.content})

    # Add the current user message
    messages.append({"role": "user", "content": "Can you please write Blender code for me that accomplishes the following task: " + prompt + "? \n. Do not respond with anything that is not Python code. Do not provide explanations"})

    response = openai.ChatCompletion.create(
        model=context.scene.gpt4_model,
        messages=messages,
        stream=True,
        max_tokens=1500,
    )

    try:
        collected_events = []
        completion_text = ''
        # iterate through the stream of events
        for event in response:
            if 'role' in event['choices'][0]['delta']:
                # skip
                continue
            if len(event['choices'][0]['delta']) == 0:
                # skip
                continue
            collected_events.append(event)  # save the event response
            event_text = event['choices'][0]['delta']['content']
            completion_text += event_text  # append the text
            print(completion_text, flush=True, end='\r')
        completion_text = re.findall(r'```(.*?)```', completion_text, re.DOTALL)[0]
        completion_text = re.sub(r'^python', '', completion_text, flags=re.MULTILINE)
        
        return completion_text
    except IndexError:
        return None

def split_area_to_text_editor(context):
    area = context.area
    for region in area.regions:
        if region.type == 'WINDOW':
            override = {'area': area, 'region': region}
            bpy.ops.screen.area_split(override, direction='VERTICAL', factor=0.5)
            break

    new_area = context.screen.areas[-1]
    new_area.type = 'TEXT_EDITOR'
    return new_area