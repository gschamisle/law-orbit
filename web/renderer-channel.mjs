// Send map data from the parent window's message event, not an iframe load callback.
// WebKit can attribute a cross-window call made in the load callback to the child.
export function createRendererChannel(origin) {
  let activeFrame = null;
  let payload;
  return {
    use(frame, data) {
      activeFrame = frame;
      payload = data;
    },
    ready(event, currentFrame) {
      if (!activeFrame || currentFrame !== activeFrame ||
          event.origin !== origin || event.source !== currentFrame.contentWindow ||
          event.data?.type !== 'galaxy-ready') return false;
      currentFrame.contentWindow.postMessage({ type: 'galaxy-data', data: payload }, origin);
      return true;
    },
  };
}
