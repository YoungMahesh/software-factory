import { describe, it, expect } from "vitest";
import {
  convertDbMessageToChatMessage,
  formatToolLabel,
  getPullRequestStatus,
  getPullRequestBadgeConfig,
  formatRelativeTime,
} from "./utils";
import { DbChatMessage } from "./types";

describe("convertDbMessageToChatMessage", () => {
  it("converts user db message to ChatMessage with milliseconds timestamp", () => {
    const dbMsg: DbChatMessage = {
      id: "msg-user-1",
      repo: "my-app",
      role: "user",
      content: "Build a login page",
      created_at: 1728639200,
    };

    const chatMsg = convertDbMessageToChatMessage(dbMsg);
    expect(chatMsg).toEqual({
      id: "msg-user-1",
      role: "user",
      text: "Build a login page",
      timestamp: 1728639200000,
    });
  });

  it("converts refusal db message to ChatMessage with refusal payload", () => {
    const dbMsg: DbChatMessage = {
      id: "msg-refusal-1",
      repo: "my-app",
      role: "assistant",
      content: "Scope refusal",
      turn_data: {
        refusal: true,
        reason: "Backend out of scope",
        category: "out_of_scope",
      },
      created_at: 1728639201000, // already in ms
    };

    const chatMsg = convertDbMessageToChatMessage(dbMsg);
    expect(chatMsg).toEqual({
      id: "msg-refusal-1",
      role: "assistant",
      text: "Scope refusal",
      timestamp: 1728639201000,
      refusal: {
        message: "Scope refusal",
        reason: "Backend out of scope",
        category: "out_of_scope",
      },
    });
  });

  it("converts grilling round db message with structured turn data", () => {
    const grillTurn = {
      type: "grill_round" as const,
      round: 1,
      summary: "Interview round 1",
      questions: [
        {
          id: "Q1",
          title: "Architecture",
          question: "Choose store",
          recommended: "Zustand",
        },
      ],
    };

    const dbMsg: DbChatMessage = {
      id: "msg-grill-1",
      repo: "my-app",
      role: "assistant",
      content: "Grilling response",
      turn_data: grillTurn,
      created_at: 1728639202,
    };

    const chatMsg = convertDbMessageToChatMessage(dbMsg);
    expect(chatMsg.id).toBe("msg-grill-1");
    expect(chatMsg.role).toBe("assistant");
    expect(chatMsg.text).toBe("Interview round 1");
    expect(chatMsg.grillTurn).toEqual(grillTurn);
    expect(chatMsg.timestamp).toBe(1728639202000);
  });

  it("converts approved plan / dispatched job message", () => {
    const dbMsg: DbChatMessage = {
      id: "msg-approved-1",
      repo: "my-app",
      role: "assistant",
      content: "Plan approved for login-v1",
      turn_data: {
        status: "approved",
        job_id: "job-12345",
      },
      created_at: 1728639203,
    };

    const chatMsg = convertDbMessageToChatMessage(dbMsg);
    expect(chatMsg.id).toBe("msg-approved-1");
    expect(chatMsg.role).toBe("assistant");
    expect(chatMsg.text).toBe("Plan approved for login-v1");
    expect(chatMsg.jobId).toBe("job-12345");
    expect(chatMsg.timestamp).toBe(1728639203000);
  });

  it("converts delivery_gate db message to ChatMessage with deliveryGate payload", () => {
    const dbMsg: DbChatMessage = {
      id: "msg-delivery-gate-1",
      repo: "my-app",
      role: "assistant",
      content: "Merged Feature Pull Request #12 into main. Live preview synchronized.",
      turn_data: {
        type: "delivery_gate",
        status: "merged",
        merged: true,
        pull_number: 12,
        sha: "abc1234",
        branch: "factory/feature-1",
        preview_synced: true,
      },
      created_at: 1728639204,
    };

    const chatMsg = convertDbMessageToChatMessage(dbMsg);
    expect(chatMsg.id).toBe("msg-delivery-gate-1");
    expect(chatMsg.role).toBe("assistant");
    expect(chatMsg.text).toBe(
      "Merged Feature Pull Request #12 into main. Live preview synchronized."
    );
    expect(chatMsg.deliveryGate).toEqual(dbMsg.turn_data);
    expect(chatMsg.turn_data).toEqual(dbMsg.turn_data);
  });
});

describe("getPullRequestStatus", () => {
  it("resolves to 'merged' when merged flag or status is set", () => {
    expect(
      getPullRequestStatus({
        number: 1,
        title: "PR 1",
        state: "closed",
        status: "merged",
        draft: false,
        merged: true,
        head_branch: "factory/feat",
        base_branch: "main",
        html_url: "https://github.com",
      })
    ).toBe("merged");

    expect(
      getPullRequestStatus(undefined, {
        status: "merged",
        merged: true,
      })
    ).toBe("merged");
  });

  it("resolves to 'closed' when PR is closed without being merged", () => {
    expect(
      getPullRequestStatus({
        number: 2,
        title: "PR 2",
        state: "closed",
        status: "ready_for_review",
        draft: false,
        merged: false,
        head_branch: "factory/feat",
        base_branch: "main",
        html_url: "https://github.com",
      })
    ).toBe("closed");
  });

  it("resolves to 'conflict' when mergeable is false or mergeable_state is dirty/conflict", () => {
    expect(
      getPullRequestStatus({
        number: 3,
        title: "PR 3",
        state: "open",
        status: "ready_for_review",
        draft: false,
        merged: false,
        mergeable: false,
        mergeable_state: "dirty",
        head_branch: "factory/feat",
        base_branch: "main",
        html_url: "https://github.com",
      })
    ).toBe("conflict");
  });

  it("resolves to 'draft' when draft flag or status is set", () => {
    expect(
      getPullRequestStatus({
        number: 4,
        title: "PR 4",
        state: "open",
        status: "draft",
        draft: true,
        merged: false,
        head_branch: "factory/feat",
        base_branch: "main",
        html_url: "https://github.com",
      })
    ).toBe("draft");
  });

  it("resolves to 'ready_for_review' for standard open mergeable PRs", () => {
    expect(
      getPullRequestStatus({
        number: 5,
        title: "PR 5",
        state: "open",
        status: "ready_for_review",
        draft: false,
        merged: false,
        mergeable: true,
        head_branch: "factory/feat",
        base_branch: "main",
        html_url: "https://github.com",
      })
    ).toBe("ready_for_review");
  });
});

describe("getPullRequestBadgeConfig", () => {
  it("returns correct labels and variants for each PullRequestStatus", () => {
    expect(getPullRequestBadgeConfig("merged")).toEqual({
      label: "Merged",
      variant: "purple",
      className: "",
    });

    expect(getPullRequestBadgeConfig("conflict")).toEqual({
      label: "Conflict",
      variant: "danger",
      className: "",
    });

    expect(getPullRequestBadgeConfig("draft")).toEqual({
      label: "Draft",
      variant: "warning",
      className: "",
    });

    expect(getPullRequestBadgeConfig("closed")).toEqual({
      label: "Closed",
      variant: "neutral",
      className: "",
    });

    expect(getPullRequestBadgeConfig("ready_for_review")).toEqual({
      label: "Ready for Review",
      variant: "success",
      className: "",
    });
  });
});

describe("formatRelativeTime", () => {
  it("formats relative timestamps correctly", () => {
    const now = Date.now();
    expect(formatRelativeTime("")).toBe("—");
    expect(formatRelativeTime("invalid-date")).toBe("—");
    expect(formatRelativeTime(new Date(now + 10000))).toBe("just now");
    expect(formatRelativeTime(new Date(now - 15000))).toBe("15s ago");
    expect(formatRelativeTime(new Date(now - 120000))).toBe("2m ago");
    expect(formatRelativeTime(new Date(now - 7200000))).toBe("2h ago");
    expect(formatRelativeTime(new Date(now - 86400000 * 3))).toBe("3d ago");
  });
});

