from typing import List, Type
from fastapi import APIRouter, HTTPException
from pydantic import ValidationError
from jvspatial.core.entities import Walker

class GraphAPI:
    def __init__(self):
        self.router = APIRouter()

    def endpoint(self, path: str, methods: List[str] = ["POST"], **kwargs):
        def decorator(cls: Type[Walker]):
            async def handler(request: dict):
                start_node = request.pop("start_node", None)
                max_nodes = request.pop("max_nodes", None)

                try:
                    walker = cls(**request)
                except ValidationError as e:
                    raise HTTPException(status_code=422, detail=e.errors())

                result = await walker.spawn(start=start_node)

                if result.response:
                    if "status" in result.response and result.response["status"] >= 400:
                        raise HTTPException(
                            status_code=result.response["status"],
                            detail=result.response.get("detail", "Unknown error"),
                        )
                    return result.response
                return {}

            self.router.add_api_route(
                path, handler, methods=methods, response_model=dict, **kwargs
            )
            return cls

        return decorator