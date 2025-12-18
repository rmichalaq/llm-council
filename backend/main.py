"""FastAPI backend for LLM Council."""

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import json
import asyncio
import base64

from . import storage
from .council import run_full_council, generate_conversation_title, stage1_collect_responses, stage2_collect_rankings, stage3_synthesize_final, calculate_aggregate_rankings

app = FastAPI(title="LLM Council API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5177", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    pass


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str
    files: Optional[List[Dict[str, Any]]] = None


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "LLM Council API"}


@app.get("/api/agents")
async def get_available_agents():
    """Get list of available agents/models from OpenRouter."""
    from .openrouter import get_available_models
    from .config import CHAIRMAN_MODEL
    
    try:
        models = await get_available_models()
        # Extract model IDs
        model_ids = [model['id'] for model in models if 'id' in model]
        
        return {
            "agents": model_ids,
            "models": models,  # Include full model data for frontend
            "default_chairman": CHAIRMAN_MODEL
        }
    except Exception as e:
        print(f"Error getting agents: {e}")
        # Fallback to config if API fails
        from .config import COUNCIL_MODELS
        return {
            "agents": COUNCIL_MODELS,
            "models": [{"id": model} for model in COUNCIL_MODELS],
            "default_chairman": CHAIRMAN_MODEL
        }


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id)
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    success = storage.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted", "conversation_id": conversation_id}


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and run the 3-stage council process.
    Returns the complete response with all stages.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    # Add user message
    storage.add_user_message(conversation_id, request.content)

    # If this is the first message, generate a title
    if is_first_message:
        title = await generate_conversation_title(request.content)
        storage.update_conversation_title(conversation_id, title)

    # Run the 3-stage council process
    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        request.content
    )

    # Add assistant message with all stages
    storage.add_assistant_message(
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result
    )

    # Return the complete response with metadata
    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(
    conversation_id: str,
    request: Request,
    content: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    selected_agents: Optional[str] = Form(None),
    chairman_model: Optional[str] = Form(None)
):
    """
    Send a message and stream the 3-stage council process.
    Returns Server-Sent Events as each stage completes.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0

    # Parse selected agents
    agents_to_use = None
    chairman_to_use = None
    if selected_agents:
        try:
            agents_to_use = json.loads(selected_agents)
        except:
            pass
    if chairman_model:
        chairman_to_use = chairman_model

    # Process files
    file_data = []
    print(f"Received {len(files)} file(s) in request")
    for file in files:
        try:
            contents = await file.read()
            print(f"Processing file: {file.filename}, size: {len(contents)} bytes, content_type: {file.content_type}")
            # Encode file content as base64 for transmission
            file_base64 = base64.b64encode(contents).decode('utf-8')
            file_data.append({
                "name": file.filename,
                "content": file_base64,
                "content_type": file.content_type or "application/octet-stream",
                "size": len(contents)
            })
        except Exception as e:
            print(f"Error processing file {file.filename}: {e}")
            # Continue with other files even if one fails

    # Create a cancellation event
    cancelled = asyncio.Event()
    
    async def check_disconnect():
        """Check if client disconnected and set cancellation event."""
        try:
            while True:
                await asyncio.sleep(0.5)  # Check every 500ms
                if await request.is_disconnected():
                    cancelled.set()
                    break
        except asyncio.CancelledError:
            pass
    
    # Start disconnect checker
    disconnect_checker = asyncio.create_task(check_disconnect())
    
    async def event_generator():
        try:
            # Build enhanced query with file content
            enhanced_query = content
            if file_data:
                file_descriptions = []
                for f in file_data:
                    file_descriptions.append(f"File: {f['name']} ({f['content_type']}, {f['size']} bytes)")
                enhanced_query = f"{content}\n\nAttached files:\n" + "\n".join(file_descriptions)
                
                # Determine text file extensions
                text_extensions = {
                    '.txt', '.md', '.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', 
                    '.json', '.xml', '.yaml', '.yml', '.csv', '.log', '.sh', '.bat', 
                    '.ps1', '.sql', '.r', '.java', '.cpp', '.c', '.h', '.hpp', '.go',
                    '.rs', '.php', '.rb', '.swift', '.kt', '.scala', '.clj', '.lua',
                    '.pl', '.pm', '.r', '.m', '.mm', '.dart', '.elm', '.ex', '.exs',
                    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'
                }
                
                # Include file content for text files or files with text-like extensions
                files_included = 0
                for f in file_data:
                    should_include = False
                    file_name = f['name'].lower()
                    
                    # Check content type
                    if f['content_type'].startswith('text/'):
                        should_include = True
                    # Check file extension
                    elif any(file_name.endswith(ext) for ext in text_extensions):
                        should_include = True
                    # Check common text-like content types
                    elif f['content_type'] in ['application/json', 'application/xml', 'application/javascript', 'application/x-yaml']:
                        should_include = True
                    # Try to decode as text for any file if content type is unknown
                    elif not f['content_type'] or f['content_type'] == 'application/octet-stream':
                        # Try to decode and see if it's valid UTF-8 text
                        try:
                            test_decode = base64.b64decode(f['content']).decode('utf-8', errors='strict')
                            # If it decodes successfully and looks like text, include it
                            if test_decode.strip() and len(test_decode) > 0:
                                should_include = True
                        except:
                            pass
                    
                    if should_include:
                        try:
                            file_text = base64.b64decode(f['content']).decode('utf-8', errors='ignore')
                            if file_text.strip():  # Only include if there's actual content
                                enhanced_query += f"\n\n--- Content of {f['name']} ---\n{file_text}"
                                files_included += 1
                            else:
                                enhanced_query += f"\n\n--- Note: File {f['name']} appears to be empty ---"
                        except Exception as e:
                            # If decoding fails, include a note about the file
                            enhanced_query += f"\n\n--- Note: Could not read content of {f['name']} (error: {str(e)}) ---"
                    else:
                        enhanced_query += f"\n\n--- Note: File {f['name']} ({f['content_type']}) appears to be binary or unsupported format. Content not included. ---"
                
                # Add summary if files were processed
                if files_included > 0:
                    enhanced_query += f"\n\n[Note: {files_included} file(s) content included above]"
                else:
                    print(f"Warning: No file content was included for {len(file_data)} file(s)")
                    enhanced_query += f"\n\n[Warning: File content could not be extracted. Please ensure files are text-based or provide file contents directly in your message.]"

            # Add user message with file metadata
            storage.add_user_message(conversation_id, content, file_data)

            # Start title generation in parallel (don't await yet)
            title_task = None
            if is_first_message:
                title_task = asyncio.create_task(generate_conversation_title(content))

            # Stage 1: Collect responses with progress tracking
            yield f"data: {json.dumps({'type': 'stage1_start', 'data': {'total': len(agents_to_use)}})}\n\n"
            
            # Track progress for each agent
            from .openrouter import query_model
            
            messages = [{"role": "user", "content": enhanced_query}]
            # Create tasks with model mapping preserved
            task_to_model = {}
            tasks = []
            for model in agents_to_use:
                task = asyncio.create_task(query_model(model, messages))
                task_to_model[task] = model
                tasks.append(task)
            
            stage1_results = []
            completed_agents = []
            completed_count = 0
            total_count = len(agents_to_use)
            
            # Use as_completed to track progress as each agent finishes
            for done_task in asyncio.as_completed(tasks):
                # Check for cancellation
                if cancelled.is_set():
                    # Cancel remaining tasks
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    yield f"data: {json.dumps({'type': 'cancelled', 'message': 'Request cancelled by user'})}\n\n"
                    return
                
                try:
                    response = await done_task
                except asyncio.CancelledError:
                    yield f"data: {json.dumps({'type': 'cancelled', 'message': 'Request cancelled'})}\n\n"
                    return
                
                # Find which model this response belongs to
                model = task_to_model.get(done_task, None)
                if model and model not in completed_agents:
                    completed_agents.append(model)
                    completed_count += 1
                    # Send progress event
                    yield f"data: {json.dumps({'type': 'stage1_progress', 'data': {'model': model, 'completed': completed_count, 'total': total_count, 'completed_agents': completed_agents.copy()}})}\n\n"
                    if response is not None:
                        stage1_results.append({
                            "model": model,
                            "response": response.get('content', '')
                        })
            
            # Check for cancellation before proceeding
            if cancelled.is_set():
                yield f"data: {json.dumps({'type': 'cancelled', 'message': 'Request cancelled by user'})}\n\n"
                return
            
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

            # Stage 2: Collect rankings
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            stage2_results, label_to_model = await stage2_collect_rankings(enhanced_query, stage1_results, agents_to_use)
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings}})}\n\n"

            # Stage 3: Synthesize final answer
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
            stage3_result = await stage3_synthesize_final(enhanced_query, stage1_results, stage2_results, chairman_to_use)
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            # Wait for title generation if it was started
            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            # Save complete assistant message
            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result
            )

            # Send completion event
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except asyncio.CancelledError:
            yield f"data: {json.dumps({'type': 'cancelled', 'message': 'Request cancelled'})}\n\n"
        except Exception as e:
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            # Clean up disconnect checker
            disconnect_checker.cancel()
            try:
                await disconnect_checker
            except asyncio.CancelledError:
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
