from __future__ import annotations

from typing import Any


class AiProductKnowledgeService:
    def build_snapshot(self) -> dict[str, Any]:
        return {
            "summary": (
                "Eazy Test Web is a web-first API testing platform for team collaboration. "
                "It manages test assets through a Project -> Suite -> Case -> Environment -> Execution -> Report workflow."
            ),
            "workflow": [
                "Project -> Suite -> Case -> Environment -> Execution -> Report -> Review",
            ],
            "core_objects": [
                "Project is the top-level container for a business domain or service area.",
                "Suite groups cases for maintenance, regression, or scenario-based execution.",
                "Case is the smallest executable API test unit with request, assertions, processors, and metadata.",
                "Environment provides runtime context such as base URL, headers, and variables.",
                "Execution records a real run and its outcome.",
                "Report stores execution artifacts such as HTML or JSON output.",
            ],
            "page_guides": {
                "general": {
                    "purpose": "Explain product capabilities, object model, and the standard testing workflow.",
                    "capabilities": [
                        "Guide users across project setup, case authoring, execution, reporting, and review.",
                        "Clarify the responsibility of each core object in the testing workflow.",
                    ],
                    "ai_capabilities": [
                        "Explain where AI can accelerate design, authoring, diagnosis, and summarization.",
                    ],
                },
                "workspace": {
                    "purpose": "Author and maintain projects, suites, and cases.",
                    "capabilities": [
                        "Manage Project, Suite, and Case assets.",
                        "Edit request method, URL, headers, body, assertions, processors, and metadata.",
                        "Import assets from Excel or legacy project.json during migration.",
                    ],
                    "ai_capabilities": [
                        "Coverage scan identifies missing coverage dimensions.",
                        "Test point generation turns gaps or markdown input into reviewable test points.",
                        "Draft generation, assertion suggestions, test data, mock templates, and execution preparation live here.",
                    ],
                },
                "environments": {
                    "purpose": "Manage reusable runtime context for executing the same cases across environments.",
                    "capabilities": [
                        "Maintain base URL, shared headers, and environment variables.",
                        "Keep environment-specific data out of individual cases whenever possible.",
                    ],
                    "ai_capabilities": [
                        "AI should treat environment data as execution context, not as hidden secret access.",
                    ],
                },
                "executions": {
                    "purpose": "Run cases or suites and diagnose execution outcomes.",
                    "capabilities": [
                        "Trigger case immediate execution.",
                        "Queue suite execution for worker consumption.",
                        "Inspect execution summaries, failed items, retry history, and detailed request/response evidence.",
                        "Cancel running work and retry terminal executions within product rules.",
                    ],
                    "ai_capabilities": [
                        "AI diagnosis helps with first-pass failure triage.",
                        "AI should reason from execution evidence and suggest the shortest next checks.",
                    ],
                },
                "reports": {
                    "purpose": "Review generated HTML or JSON reports and produce shareable summaries.",
                    "capabilities": [
                        "Preview and open HTML or JSON report artifacts.",
                        "Use reports as the durable output of execution and review.",
                    ],
                    "ai_capabilities": [
                        "AI report summary compresses technical results into business-readable conclusions.",
                    ],
                },
                "audit_logs": {
                    "purpose": "Provide governance and traceability for important operations.",
                    "capabilities": [
                        "Track who changed assets, ran imports, used AI actions, or performed governance-sensitive operations.",
                        "Support review of operational history instead of hidden system inspection.",
                    ],
                    "ai_capabilities": [
                        "AI can explain visible governance implications but must not invent hidden audit entries.",
                    ],
                },
                "users": {
                    "purpose": "Manage accounts and role-based access boundaries.",
                    "capabilities": [
                        "Admin manages accounts, roles, and active state.",
                        "Tester maintains test assets and runs executions.",
                        "Developer is primarily read-only for collaboration and review.",
                    ],
                    "ai_capabilities": [
                        "AI can explain permission boundaries and operational guidance, not fabricate account state.",
                    ],
                },
            },
            "ai_operating_model": {
                "summary": "AI is copilot, not autopilot.",
                "rules": [
                    "AI suggests, supplements, diagnoses, and summarizes.",
                    "AI does not replace final human judgment.",
                    "AI should not silently rewrite execution results or hidden system state.",
                    "Saved AI artifacts are reviewed and applied explicitly by users.",
                ],
            },
            "known_limits": [
                "Legacy import support is a migration bridge, not a long-term primary workflow.",
                "Current AI execution preparation is case-first, not a full suite orchestration system.",
                "AI mock support manages reusable templates, not a complete runtime mock platform.",
            ],
            "role_boundaries": [
                "admin can manage users and audit-related governance surfaces.",
                "tester can maintain assets and run executions but does not manage users.",
                "developer is mainly read-only for workspace, executions, and reports.",
            ],
        }
