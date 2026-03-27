from fastapi import APIRouter

from backend.app.core.error_handling import build_api_error_responses
from backend.app.api.routes import ai_case_drafts, ai_copilot, audit_logs, auth, cases, environments, executions, health, imports, projects, reports, scheduled_jobs, suites, users

api_router = APIRouter()
common_error_responses = build_api_error_responses()

api_router.include_router(health.router, prefix="/health", tags=["health"], responses=common_error_responses)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"], responses=common_error_responses)
api_router.include_router(audit_logs.router, prefix="/audit-logs", tags=["audit_logs"], responses=common_error_responses)
api_router.include_router(users.router, prefix="/users", tags=["users"], responses=common_error_responses)
api_router.include_router(projects.router, prefix="/projects", tags=["projects"], responses=common_error_responses)
api_router.include_router(suites.router, prefix="/suites", tags=["suites"], responses=common_error_responses)
api_router.include_router(cases.router, prefix="/cases", tags=["cases"], responses=common_error_responses)
api_router.include_router(environments.router, prefix="/environments", tags=["environments"], responses=common_error_responses)
api_router.include_router(executions.router, prefix="/executions", tags=["executions"], responses=common_error_responses)
api_router.include_router(scheduled_jobs.router, prefix="/scheduled-jobs", tags=["scheduled_jobs"], responses=common_error_responses)
api_router.include_router(reports.router, prefix="/reports", tags=["reports"], responses=common_error_responses)
api_router.include_router(imports.router, prefix="/imports", tags=["imports"], responses=common_error_responses)
api_router.include_router(ai_case_drafts.router, prefix="/ai-case-drafts", tags=["ai_case_drafts"], responses=common_error_responses)
api_router.include_router(ai_copilot.router, prefix="/ai-copilot", tags=["ai_copilot"], responses=common_error_responses)
