from app.router.schemas import RouterProposal


def reanalysis_reason(proposal: RouterProposal) -> str | None:
    relevant = set(proposal.scenarios or proposal.alternatives)
    checks = [b for b in proposal.boundary_checks if b.scenario_id in relevant]
    # Missing facts always win over an invitation to 'think harder'.
    if any(b.status == "missing" for b in checks):
        return None
    if any(b.status == "conflicting" for b in checks):
        return "Conflicting supplied evidence on a relevant scenario boundary; resolve corrections or clarify"
    return None
