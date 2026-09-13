"""Native provider wire formats. Gemini model parts/signatures stay intact in memory."""
import copy
import json
import uuid


def conversation(value):
    return [{'role': 'user', 'content': value}] if isinstance(value, str) else value


def gemini_contents(messages):
    from google.genai import types
    contents = []
    for message in conversation(messages):
        if 'gemini_content' in message:
            contents.append(message['gemini_content'])
        elif message['role'] == 'tool':
            part = types.Part(function_response=types.FunctionResponse(
                name=message['name'], id=message.get('native_call_id'), response=message['observation']))
            if contents and contents[-1].role == 'user' and contents[-1].parts[0].function_response:
                contents[-1].parts.append(part)
            else:
                contents.append(types.Content(role='user', parts=[part]))
        else:
            contents.append(types.Content(role='model' if message['role'] == 'assistant' else 'user',
                                          parts=[types.Part(text=message.get('content') or ' ')]))
    return contents


def gemini_tool_declarations(schema):
    """Adapt the portable JSON Schema to Gemini's supported function-declaration subset."""
    declarations = copy.deepcopy(schema)

    def remove_unsupported(node):
        if isinstance(node, dict):
            # `additionalProperties` is valid JSON Schema/OpenAI input but rejected by Gemini.
            node.pop('additionalProperties', None)
            for value in node.values():
                remove_unsupported(value)
        elif isinstance(node, list):
            for value in node:
                remove_unsupported(value)

    remove_unsupported(declarations)
    return declarations


def openai_messages(messages, system_prompt):
    result = [{'role': 'system', 'content': system_prompt}] if system_prompt else []
    for message in conversation(messages):
        if message['role'] == 'tool':
            result.append({'role': 'tool', 'tool_call_id': message['tool_call_id'],
                           'content': json.dumps(message['observation'], ensure_ascii=False)})
        else:
            item = {'role': message['role'], 'content': message.get('content')}
            if message.get('tool_calls'):
                item['tool_calls'] = message['tool_calls']
            result.append(item)
    return result


def gemini_generate(provider, messages, schema, system_prompt):
    from google import genai
    from google.genai import types
    if not provider.api_key:
        raise RuntimeError('Missing Gemini key')
    if not hasattr(provider, '_client'):
        provider._client = genai.Client(api_key=provider.api_key, http_options=types.HttpOptions(
            timeout=60000, retry_options=types.HttpRetryOptions(attempts=1)))
    response = provider._client.models.generate_content(
        model=provider.model_name, contents=gemini_contents(messages),
        config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.2,
            tools=[types.Tool(function_declarations=gemini_tool_declarations(schema))] if schema else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)))
    if not response.candidates or not response.candidates[0].content:
        raise ValueError('Empty Gemini candidate')
    content = response.candidates[0].content
    visible = ''.join(p.text for p in content.parts or [] if p.text and not p.thought)
    calls = []
    for part in content.parts or []:
        call = part.function_call
        if call:
            calls.append({'id': call.id or uuid.uuid4().hex, 'native_call_id': call.id,
                          'tool_name': call.name, 'arguments': dict(call.args or {})})
    return {'type': 'tool_call' if calls else 'text', 'calls': calls, 'content': visible,
            'decision_summary': visible if calls else '',
            'native_message': {'role': 'assistant', 'content': visible, 'gemini_content': content}}


def openai_generate(provider, messages, schema, system_prompt):
    from openai import OpenAI
    if not provider.api_key:
        raise RuntimeError('Missing OpenAI key')
    if not hasattr(provider, '_client'):
        provider._client = OpenAI(api_key=provider.api_key, max_retries=0, timeout=60)
    options = dict(model=provider.model_name, messages=openai_messages(messages, system_prompt))
    if schema:
        options.update(tools=[{'type': 'function', 'function': tool} for tool in schema],
                       tool_choice='auto', parallel_tool_calls=False)
    response = provider._client.chat.completions.create(**options)
    msg = response.choices[0].message
    native_calls, calls = [], []
    for call in msg.tool_calls or []:
        native_calls.append({'id': call.id, 'type': 'function',
                             'function': {'name': call.function.name, 'arguments': call.function.arguments}})
        try:
            arguments = json.loads(call.function.arguments)
        except (ValueError, TypeError):
            arguments = None
        calls.append({'id': call.id, 'tool_name': call.function.name, 'arguments': arguments})
    native = {'role': 'assistant', 'content': msg.content}
    if native_calls:
        native['tool_calls'] = native_calls
    return {'type': 'tool_call' if calls else 'text', 'calls': calls, 'content': msg.content or '',
            'decision_summary': (msg.content or '') if calls else '', 'native_message': native}
