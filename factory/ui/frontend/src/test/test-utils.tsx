import React, { ReactElement } from "react";
import { render, RenderOptions } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StudioProvider, StudioContextValue } from "../context/StudioContext";
import { Repo } from "../types";

export const defaultMockRepos: Repo[] = [
  { name: "cool-app", is_tanstack_compatible: true },
  { name: "test-app", is_tanstack_compatible: false },
];

export const createDefaultStudioContext = (
  overrides: Partial<StudioContextValue> = {}
): StudioContextValue => ({
  repos: defaultMockRepos,
  selectedRepo: "cool-app",
  onSelectRepo: vi.fn(),
  onCreateRepo: vi.fn().mockResolvedValue(undefined),
  activeJob: null,
  messages: [],
  onSendPrompt: vi.fn(),
  onCancelJob: vi.fn(),
  onOpenDrawer: vi.fn(),
  isSending: false,
  previewState: null,
  onLaunchPreview: vi.fn(),
  onStopPreview: vi.fn(),
  onRetryPreview: vi.fn(),
  onReconnectPreview: vi.fn(),
  refreshKey: 0,
  isLaunchingPreview: false,
  onClearChat: vi.fn().mockResolvedValue(undefined),
  isClearingChat: false,
  isChatCleared: false,
  onOpenIssueDrawer: vi.fn(),
  onCloseIssueDrawer: vi.fn(),
  onInstantDispatch: vi.fn().mockResolvedValue(undefined),
  isDispatching: false,
  branches: undefined,
  onSelectBranch: undefined,
  isSwitchingBranch: false,
  ...overrides,
});

export const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: Infinity,
      },
      mutations: {
        retry: false,
      },
    },
  });

export interface RenderWithProvidersOptions extends Omit<RenderOptions, "wrapper"> {
  contextOverrides?: Partial<StudioContextValue>;
  queryClient?: QueryClient;
}

export function renderWithProviders(
  ui: ReactElement,
  options: RenderWithProvidersOptions = {}
) {
  const {
    contextOverrides,
    queryClient = createTestQueryClient(),
    ...renderOptions
  } = options;

  let currentContext = createDefaultStudioContext(contextOverrides);

  const Wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
    <QueryClientProvider client={queryClient}>
      <StudioProvider value={currentContext}>{children}</StudioProvider>
    </QueryClientProvider>
  );

  const utils = render(ui, { wrapper: Wrapper, ...renderOptions });
  const user = userEvent.setup();

  const rerenderWithContext = (newOverrides: Partial<StudioContextValue>, newUi: ReactElement = ui) => {
    currentContext = { ...currentContext, ...newOverrides };
    return utils.rerender(
      <QueryClientProvider client={queryClient}>
        <StudioProvider value={currentContext}>{newUi}</StudioProvider>
      </QueryClientProvider>
    );
  };

  return {
    ...utils,
    user,
    queryClient,
    get context() {
      return currentContext;
    },
    rerenderWithContext,
  };
}

export * from "@testing-library/react";
export { userEvent };
