/* Owns one Launch Request observation, including every asynchronous effect. */
function createLaunchObserver({ request, publish, refresh, setRequestId, navigate,
                                schedule = setTimeout, cancel = clearTimeout,
                                reportError = console.error, interval = 1500 }) {
  let active = null;
  const handedOff = new Set();

  function stop() {
    const previous = active;
    active = null;
    if (previous) {
      previous.controller.abort();
      if (previous.timer !== null) cancel(previous.timer);
    }
  }

  async function poll(session) {
    if (active !== session) return;
    let terminal = false;
    try {
      const response = await request(session.id, session.controller.signal);
      if (active !== session) return;
      if (response.status === 404) {
        terminal = true;
        publish(null);
        setRequestId(null);
        return;
      }
      if (!response.ok) throw new Error(`Launch status request failed (${response.status})`);
      const data = await response.json();
      if (active !== session) return;
      publish(data);
      terminal = ['ready', 'failed'].includes(data.request?.status);
      if (terminal) {
        await refresh();
        if (active !== session) return;
        if (data.request.status === 'ready' && data.request.handoff_url && !handedOff.has(session.id)) {
          handedOff.add(session.id);
          setRequestId(null);
          navigate(data.request.handoff_url);
        }
      }
    } catch (error) {
      if (active === session && error.name !== 'AbortError') reportError(error);
    } finally {
      // Schedule after completion: slow requests never overlap or reorder.
      if (active === session && !terminal) {
        session.timer = schedule(() => poll(session), interval);
      }
    }
  }

  return {
    track(requestId) {
      if (!requestId) return Promise.resolve();
      stop();
      publish(null);
      const session = { id: requestId, controller: new AbortController(), timer: null };
      active = session;
      setRequestId(requestId);
      return poll(session);
    },
    dismiss() {
      stop();
      publish(null);
      setRequestId(null);
    },
    destroy: stop,
  };
}
