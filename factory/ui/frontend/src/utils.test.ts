import { describe, it, expect } from "vitest";
import { convertDbMessageToChatMessage, formatToolLabel } from "./utils";
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
});
