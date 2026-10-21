from fastapi import APIRouter

from app.modules.access.router import router as access_router
from app.modules.actions.router import router as actions_router
from app.modules.agent.router import router as agent_router
from app.modules.ai.router import router as ai_router
from app.modules.evidence.router import router as evidence_router
from app.modules.hub.safety import router as safety_router
from app.modules.hub.suggestions import router as suggestions_router
from app.modules.monitoring.router import router as monitoring_router
from app.modules.voice.router import router as voice_router
from app.modules.auth.router import router as auth_router
from app.modules.documents.router import router as documents_router
from app.modules.frontend_data.router import router as frontend_data_router
from app.modules.health.router import router as health_router
from app.modules.intelligence.router import router as intelligence_router
from app.modules.inventory.router import router as inventory_router
from app.modules.notifications.router import router as notifications_router
from app.modules.procurement.compat_router import router as procurement_compat_router
from app.modules.procurement.router import router as procurement_router
from app.modules.projects.router import router as projects_router
from app.modules.reports.router import router as reports_router
from app.modules.resources.router import router as resources_router
from app.modules.workforce.router import router as workforce_router
from app.modules.tasks.router import router as tasks_router

api_router = APIRouter()

# Auth routes
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])

# Frontend-friendly MongoDB data routes
api_router.include_router(frontend_data_router, prefix="/frontend-data", tags=["Frontend Data"])

# Health check
api_router.include_router(health_router, prefix="/health", tags=["Health"])

# Projects
api_router.include_router(projects_router, prefix="/projects", tags=["Projects"])

# Workforce
api_router.include_router(workforce_router, prefix="/workforce", tags=["Workforce"])
# Tasks
api_router.include_router(tasks_router, prefix="/tasks", tags=["Tasks"])

# Inventory
api_router.include_router(inventory_router, prefix="/inventory", tags=["Inventory"])

# Resources
api_router.include_router(resources_router, prefix="/resources", tags=["Resources"])

# Procurement
api_router.include_router(procurement_router, prefix="/procurement", tags=["Procurement"])
api_router.include_router(procurement_compat_router, tags=["Procurement Compat"])

# Notifications
api_router.include_router(notifications_router, prefix="/notifications", tags=["Notifications"])

# Reports
api_router.include_router(reports_router, prefix="/reports", tags=["Reports"])

# Documents
api_router.include_router(documents_router, prefix="/documents", tags=["Documents"])

# AI Site Assistant (Phase 2) and operations intelligence (Phases 4-5)
api_router.include_router(agent_router, prefix="/ai/agent", tags=["AI Agent mode"])
api_router.include_router(ai_router, prefix="/ai", tags=["AI Assistant"])
api_router.include_router(intelligence_router, prefix="/intelligence", tags=["Intelligence"])
api_router.include_router(actions_router, prefix="/recommendations", tags=["Action Center"])
api_router.include_router(monitoring_router, prefix="/monitoring", tags=["Monitoring"])
api_router.include_router(evidence_router, prefix="/evidence", tags=["Progress Evidence"])
api_router.include_router(suggestions_router, prefix="/hub/suggestions", tags=["Innovation Hub"])
api_router.include_router(safety_router, prefix="/hub/safety", tags=["Safety"])
api_router.include_router(voice_router, prefix="/voice", tags=["Voice Calls"])
api_router.include_router(access_router, prefix="/access", tags=["Access Control"])
