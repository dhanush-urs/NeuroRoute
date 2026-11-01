"""
NVIDIA NIM Explanation Service for NeuroRoute.

This service provides AI-generated explanations for routing decisions,
traffic conditions, and what-if scenarios using NVIDIA NIM hosted API.
Falls back to deterministic templates when NIM is unavailable.
"""

import os
import json
import asyncio
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ExplanationProvider(str, Enum):
    """Supported explanation providers."""
    NVIDIA_NIM = "nvidia_nim"
    TEMPLATE = "template"


@dataclass
class ExplanationRequest:
    """Request for generating an explanation."""
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


@dataclass
class ExplanationResponse:
    """Response containing the generated explanation."""
    explanation: str
    provider: ExplanationProvider
    model_used: Optional[str] = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    facts_used: Dict[str, Any] = field(default_factory=dict)
    fallback_used: bool = False


class ExplanationService:
    """Service for generating AI explanations using NVIDIA NIM or template fallback."""
    
    def __init__(self):
        try:
            settings = get_settings()
            default_key = settings.nvidia_api_key
            default_url = settings.nvidia_nim_url
            default_model = settings.nvidia_nim_model
            default_timeout = settings.nvidia_nim_timeout
        except Exception:
            default_key = None
            default_url = "https://integrate.api.nvidia.com/v1"
            default_model = "nvidia/nemotron-3-ultra-550b-a55b"
            default_timeout = 15.0

        self.api_key = os.getenv("NVIDIA_API_KEY") or default_key
        self.nim_url = os.getenv("NVIDIA_NIM_URL") or default_url
        self.model = os.getenv("NVIDIA_NIM_MODEL") or default_model
        # If user/env passed legacy shorthand, translate to hosted NIM model name
        if self.model in ("nemotron-3-ultra", "nvidia/nemotron-3-ultra"):
            self.model = "nvidia/nemotron-3-ultra-550b-a55b"
        self.timeout = float(os.getenv("NVIDIA_NIM_TIMEOUT") or default_timeout)
        self.enabled = bool(self.api_key)
        
        # HTTP client for NIM API
        self._client: Optional[httpx.AsyncClient] = None
        
        logger.info(f"ExplanationService initialized - NVIDIA NIM: {'enabled' if self.enabled else 'disabled'}")
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for NIM API."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.nim_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _build_prompt(self, request: ExplanationRequest) -> str:
        """Build the prompt for the LLM based on structured facts."""
        facts = []
        
        # Route information
        if request.recommended_route:
            route = request.recommended_route
            facts.append(f"Recommended route: {route.get('algorithm', 'unknown')} algorithm")
            facts.append(f"Distance: {route.get('distance_km', 0):.1f} km")
            facts.append(f"Current ETA: {route.get('current_eta_sec', 0)//60} min {route.get('current_eta_sec', 0)%60} sec")
            facts.append(f"Predicted ETA: {route.get('predicted_eta_sec', 0)//60} min {route.get('predicted_eta_sec', 0)%60} sec")
            facts.append(f"Congestion risk: {route.get('congestion_risk', 'unknown')}")
        
        # Alternative routes
        if request.alternative_routes:
            alt = request.alternative_routes[0] if request.alternative_routes else None
            if alt:
                facts.append(f"Alternative route: {alt.get('algorithm', 'unknown')} algorithm")
                facts.append(f"Alternative distance: {alt.get('distance_km', 0):.1f} km")
                facts.append(f"Alternative predicted ETA: {alt.get('predicted_eta_sec', 0)//60} min")
        
        # Traffic conditions
        if request.current_congestion:
            facts.append(f"Current congestion level: {request.current_congestion.get('level', 'unknown')}")
            facts.append(f"Current congestion score: {request.current_congestion.get('score', 0):.2f}")
        
        if request.predicted_congestion:
            facts.append(f"Predicted congestion level: {request.predicted_congestion.get('level', 'unknown')}")
            facts.append(f"Predicted congestion score: {request.predicted_congestion.get('score', 0):.2f}")
        
        # Incidents
        if request.active_incidents:
            incident = request.active_incidents[0]
            facts.append(f"Active incident: {incident.get('type', 'unknown')} on road {incident.get('road_id', 'unknown')}")
            facts.append(f"Incident severity: {incident.get('severity', 0):.1f}")
            facts.append(f"Capacity reduction: {incident.get('capacity_reduction_pct', 0)}%")
        
        if request.affected_road_id:
            facts.append(f"Affected road: {request.affected_road_id}")
        
        # Weather
        if request.weather_condition:
            facts.append(f"Weather: {request.weather_condition}")
        if request.weather_severity:
            facts.append(f"Weather severity: {request.weather_severity}")
        
        # Routing decision
        if request.reroute_reason:
            facts.append(f"Reroute reason: {request.reroute_reason}")
        if request.eta_difference_seconds is not None:
            diff = request.eta_difference_seconds
            facts.append(f"ETA difference: {abs(diff)//60} min {abs(diff)%60} sec {'faster' if diff < 0 else 'slower'}")
        if request.congestion_difference is not None:
            facts.append(f"Congestion difference: {request.congestion_difference:.2f}")
        
        # What-if scenario
        if request.what_if_scenario:
            facts.append(f"What-if scenario: {request.what_if_scenario.get('type', 'unknown')}")
        if request.what_if_comparison:
            comp = request.what_if_comparison
            facts.append(f"What-if congestion change: {comp.get('congestion_change', 0):.3f}")
            facts.append(f"What-if vehicle change: {comp.get('vehicle_change', 0)}")
        
        # Context
        if request.road_name:
            facts.append(f"Road: {request.road_name}")
        if request.origin_name:
            facts.append(f"Origin: {request.origin_name}")
        if request.destination_name:
            facts.append(f"Destination: {request.destination_name}")
        
        # Build the prompt
        system_prompt = """You are an AI traffic assistant for NeuroRoute, an intelligent traffic routing system. 
Your task is to provide clear, concise, and helpful explanations of traffic conditions and routing decisions.
Use only the facts provided. Do not speculate or invent information.
If a fact is not provided, do not mention it. Be concise and helpful.
Format your response as a clear, natural paragraph suitable for a traffic dashboard.
Do not use bullet points or numbered lists. Write in a professional but accessible tone."""
        
        user_prompt = "Based on the following traffic facts, explain the current situation and routing recommendation:\n\n" + "\n".join(f"- {fact}" for fact in facts)
        
        return f"{system_prompt}\n\n{user_prompt}"
    
    def _build_template_explanation(self, request: ExplanationRequest) -> str:
        """Generate a deterministic template-based explanation."""
        parts = []
        
        # Route summary
        if request.recommended_route:
            route = request.recommended_route
            algo = route.get('algorithm', 'the selected algorithm')
            distance = route.get('distance_km', 0)
            current_eta = route.get('current_eta_sec', 0)
            pred_eta = route.get('predicted_eta_sec', 0)
            risk = route.get('congestion_risk', 'unknown')
            
            parts.append(f"The recommended route uses {algo}, covering {distance:.1f} km.")
            parts.append(f"Current estimated travel time is {current_eta//60} min {current_eta%60} sec, with a predicted time of {pred_eta//60} min {pred_eta%60} sec.")
            parts.append(f"Congestion risk is assessed as {risk}.")
        
        # Alternative route comparison
        if request.alternative_routes and request.recommended_route:
            rec = request.recommended_route
            alt = request.alternative_routes[0]
            
            rec_pred = rec.get('predicted_eta_sec', 0)
            alt_pred = alt.get('predicted_eta_sec', 0)
            diff = rec_pred - alt_pred
            
            if abs(diff) > 60:
                if diff > 0:
                    parts.append(f"The alternative route saves approximately {diff//60} minutes.")
                else:
                    parts.append(f"The recommended route is {abs(diff)//60} minutes faster than the alternative.")
        
        # Incident explanation
        if request.active_incidents:
            incident = request.active_incidents[0]
            inc_type = incident.get('type', 'incident')
            severity = incident.get('severity', 0)
            cap_red = incident.get('capacity_reduction_pct', 0)
            
            parts.append(f"An {inc_type} has been reported with severity {severity:.1f}, reducing road capacity by {cap_red}%.")
        
        # Weather
        if request.weather_condition and request.weather_condition != 'clear':
            parts.append(f"Current weather conditions ({request.weather_condition}) are affecting traffic flow.")
        
        # Reroute reason
        if request.reroute_reason:
            parts.append(f"The system recommended a reroute: {request.reroute_reason}.")
        
        # ETA difference
        if request.eta_difference_seconds is not None:
            diff = request.eta_difference_seconds
            if diff > 60:
                parts.append(f"This route saves approximately {diff//60} minutes compared to the alternative.")
            elif diff < -60:
                parts.append(f"The alternative route is {abs(diff)//60} minutes faster.")
        
        # What-if scenario
        if request.what_if_scenario:
            scenario = request.what_if_scenario
            parts.append(f"What-if analysis: A {scenario.get('type', 'scenario')} was simulated.")
            if request.what_if_comparison:
                comp = request.what_if_comparison
                parts.append(f"The simulation predicts a congestion change of {comp.get('congestion_change', 0):.2f} and vehicle count change of {comp.get('vehicle_change', 0)}.")
        
        # Congestion explanation
        if request.current_congestion or request.predicted_congestion:
            current = request.current_congestion.get('level', 'unknown') if request.current_congestion else 'unknown'
            predicted = request.predicted_congestion.get('level', 'unknown') if request.predicted_congestion else 'unknown'
            if current != predicted:
                parts.append(f"Congestion is expected to change from {current} to {predicted}.")
        
        return " ".join(parts) if parts else "No specific traffic information available for this route."
    
    async def generate_explanation(self, request: ExplanationRequest) -> ExplanationResponse:
        """Generate an explanation using NVIDIA NIM or template fallback."""
        facts_used = self._extract_facts(request)
        
        # Try NVIDIA NIM first if enabled
        if self.enabled:
            try:
                return await self._generate_with_nim(request, facts_used)
            except Exception as e:
                logger.warning(f"NVIDIA NIM explanation failed, falling back to template: {e}")
        
        # Fallback to template
        response = self._generate_with_template(request, facts_used)
        # Mark as fallback if NIM was enabled but failed
        response.fallback_used = self.enabled
        return response
    
    def _extract_facts(self, request: ExplanationRequest) -> Dict[str, Any]:
        """Extract all facts from the request for logging/debugging."""
        facts = {}
        if request.recommended_route:
            facts['recommended_route'] = request.recommended_route
        if request.alternative_routes:
            facts['alternative_routes'] = request.alternative_routes
        if request.current_congestion:
            facts['current_congestion'] = request.current_congestion
        if request.predicted_congestion:
            facts['predicted_congestion'] = request.predicted_congestion
        if request.active_incidents:
            facts['active_incidents'] = request.active_incidents
        if request.weather_condition:
            facts['weather_condition'] = request.weather_condition
        if request.reroute_reason:
            facts['reroute_reason'] = request.reroute_reason
        if request.eta_difference_seconds is not None:
            facts['eta_difference_seconds'] = request.eta_difference_seconds
        if request.what_if_scenario:
            facts['what_if_scenario'] = request.what_if_scenario
        return facts
    
    async def _generate_with_nim(self, request: ExplanationRequest, facts_used: Dict) -> ExplanationResponse:
        """Generate explanation using NVIDIA NIM API."""
        client = await self._get_client()
        prompt = self._build_prompt(request)
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an AI traffic assistant for NeuroRoute. Provide clear, concise explanations of traffic conditions and routing decisions based only on the facts provided. Be concise, professional, and helpful. Do not speculate or invent information."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 500,
            "top_p": 0.9,
        }
        
        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        
        data = response.json()
        message = data["choices"][0]["message"]
        content = message.get("content")
        if not content:
            content = message.get("reasoning_content") or ""
        explanation = content.strip()
        
        return ExplanationResponse(
            explanation=explanation,
            provider=ExplanationProvider.NVIDIA_NIM,
            model_used=self.model,
            facts_used=facts_used,
            fallback_used=False
        )
    
    def _generate_with_template(self, request: ExplanationRequest, facts_used: Dict) -> ExplanationResponse:
        """Generate explanation using deterministic template."""
        explanation = self._build_template_explanation(request)
        
        return ExplanationResponse(
            explanation=explanation,
            provider=ExplanationProvider.TEMPLATE,
            model_used="deterministic_template",
            facts_used=facts_used,
            fallback_used=not self.enabled
        )


# Global instance
_explanation_service: Optional["ExplanationService"] = None


def get_explanation_service() -> ExplanationService:
    """Get the global explanation service instance."""
    global _explanation_service
    if _explanation_service is None:
        _explanation_service = ExplanationService()
    return _explanation_service


async def close_explanation_service():
    """Close the explanation service."""
    global _explanation_service
    if _explanation_service:
        await _explanation_service.close()
        _explanation_service = None