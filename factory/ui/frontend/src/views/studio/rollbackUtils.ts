import { ChatMessage, PullRequest, RollbackTarget } from "../../types";

export function getLatestRollbackTarget(
  messages: ChatMessage[],
  activeBranch?: string | null,
  pullRequests: PullRequest[] = []
): { target: RollbackTarget | null; isMerged: boolean } {
  const targetMsg = [...messages].reverse().find((m) => {
    if (m.role !== "assistant") return false;
    const tData = m.turn_data || {};
    if (tData.reverted || tData.refusal || tData.type === "turn_rollback") return false;
    const isCodeProducing = Boolean(
      tData.commit_sha ||
      tData.sha ||
      tData.job_id ||
      tData.issue ||
      tData.issue_number ||
      m.jobId ||
      m.deliveryGate
    );
    if (!isCodeProducing) return false;
    if (activeBranch && tData.branch && tData.branch !== activeBranch) return false;
    return true;
  });

  if (!targetMsg) {
    return { target: null, isMerged: false };
  }

  const tData = targetMsg.turn_data || {};
  const dGate = targetMsg.deliveryGate;

  const branch = activeBranch || tData.branch || dGate?.branch;
  const commitSha = tData.commit_sha || tData.sha || dGate?.sha || null;
  const issueNumber =
    tData.issue_number ||
    tData.issue?.number ||
    dGate?.resolved_issues?.[0] ||
    null;
  const issueTitle =
    tData.issue?.title ||
    dGate?.pull_request?.title ||
    null;

  let isMerged = Boolean(dGate?.merged || dGate?.pull_request?.merged);
  if (!isMerged && branch) {
    const matchingPr = pullRequests.find(
      (p) => p.head_branch === branch || (p.head_branch && branch.endsWith(p.head_branch))
    );
    if (matchingPr?.merged) {
      isMerged = true;
    }
  }

  return {
    target: {
      messageId: targetMsg.id,
      branch: branch || undefined,
      commitSha,
      issueNumber,
      issueTitle,
    },
    isMerged,
  };
}
