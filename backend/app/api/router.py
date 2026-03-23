from fastapi import APIRouter

from backend.app.api.routes import audit_logs, auth, cases, environments, executions, health, imports, projects, reports, suites, users

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(audit_logs.router, prefix="/audit-logs", tags=["audit_logs"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(suites.router, prefix="/suites", tags=["suites"])
api_router.include_router(cases.router, prefix="/cases", tags=["cases"])
api_router.include_router(environments.router, prefix="/environments", tags=["environments"])
api_router.include_router(executions.router, prefix="/executions", tags=["executions"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(imports.router, prefix="/imports", tags=["imports"])
