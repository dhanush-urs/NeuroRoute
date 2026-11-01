"""
API routes for AI-generated traffic explanations using NVIDIA NIM.
"""

import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from app.ai.explanation import (
    ExplanationService,
    get_explanation_service,
    ExplanationRequest,
    ExplanationProvider,
    ExplanationResponse,
)

router = APIRouter(prefix="/explanations", tags=["explanations"])


class ExplanationRequestModel(BaseModel):
    """Request model for generating an explanation."""
    # Route information
    recommended_route: Optional[Dict[str, Any]] = None
    alternative_routes: Optional[List[Dict[str, Any]]] = None
    
    # Traffic conditions
    current_congestion: Optional[Dict[str, Any]] = None
    predicted_congestion: Optional[Dict[str, Any]] = None
    
    # Incident information
    active_incidents: Optional[List[Dict[str, Any]]] = None
    affected_road_id: Optional[str] = None
    
    # Weather conditions
    weather_condition: Optional[str] = None
    weather_severity: Optional[str] = None
    
    # Routing decision
    reroute_reason: Optional[str] = None
    eta_difference_seconds: Optional[int] = None
    congestion_difference: Optional[float] = None
    
    # What-if scenario
    what_if_scenario: Optional[Dict[str, Any]] = None
    what_if_comparison: Optional[Dict[str, Any]] = None
    
    # Context
    road_name: Optional[str] = None
    origin_name: Optional[str] = None
    destination_name: Optional[str] = None


class ExplanationResponseModel(BaseModel):
    """Response model for explanation generation."""
    explanation: str
    provider: str
    model_used: Optional[str] = None
    generated_at: str
    facts_used: Dict[str, Any] = {}
    fallback_used: bool = False


@router.post("/generate", response_model=ExplanationResponseModel)
async def generate_explanation(
    request: ExplanationRequestModel,
):
    """Generate an AI explanation for traffic conditions and routing decisions.
    
    This endpoint accepts structured traffic facts and returns a natural language
    explanation using NVIDIA NIM (if configured) or a deterministic template fallback.
    """
    service = get_explanation_service()
    
    # Convert request model to internal request
    request = ExplanationRequest(
        recommended_route=request.recommended_route,
        alternative_routes=request.alternative_routes,
        current_congestion=request.current_congestion,
        predicted_congestion=request.predicted_congestion,
        active_incidents=request.active_incidents,
        affected_road_id=request.affected_road_id,
        weather_condition=request.weather_condition,
        weather_severity=request.weather_severity,
        reroute_reason=request.reroute_reason,
        eta_difference_seconds=request.eta_difference_seconds,
        congestion_difference=request.congestion_difference,
        what_if_scenario=request.what_if_scenario,
        what_if_comparison=request.what_if_comparison,
        road_name=request.road_name,
        origin_name=request.origin_name,
        destination_name=request.destination_name,
    )
    
    try:
        response = await service.generate_explanation(request)
        return ExplanationResponseModel(
            explanation=response.explanation,
            provider=response.provider.value,
            model_used=response.model_used,
            generated_at=response.generated_at.isoformat(),
            facts_used=response.facts_used,
            fallback_used=response.fallback_used,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Explanation generation failed: {str(e)}")


@router.get("/models")
async def get_available_models():
    """Get information about available explanation providers."""
    service = get_explanation_service()
    
    return {
        "providers": [
            {
                "name": "template",
                "type": "deterministic_template",
                "description": "Deterministic template-based explanations using structured facts",
                "available": True,
                "requires_network": False,
            },
            {
                "name": "nvidia_nim",
                "type": "nvidia_nim",
                "description": "NVIDIA NIM hosted LLM for natural language explanations",
                "available": service.enabled,
                "requires_network": True,
                "model": service.model,
            }
        ],
        "active_provider": "nvidia_nim" if service.enabled else "template",
    }


@router.get("/health")
async def health_check():
    """Health check for explanation service."""
    service = get_explanation_service()
    
    nim_available = service.enabled
    
    return {
        "status": "healthy",
        "template_fallback": "available",
        "nvidia_nim": {
            "configured": service.enabled,
            "model": service.model,
            "endpoint": service.nim_url,
        },
        "active_provider": "nvidia_nim" if nim_available else "template",
    }