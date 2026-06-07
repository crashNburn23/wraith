import { createContext, useContext, useState, useCallback } from "react";

const Ctx = createContext(null);

export function EntityModalProvider({ children }) {
  const [target, setTarget] = useState(null);

  const open = useCallback((type, id, label) => setTarget({ type, id, label }), []);
  const close = useCallback(() => setTarget(null), []);

  return (
    <Ctx.Provider value={{ open, close }}>
      {children}
      {target && <EntityModalPortal {...target} onClose={close} />}
    </Ctx.Provider>
  );
}

export const useEntityModal = () => useContext(Ctx);

// Lazy import so the modal bundle isn't always loaded
import EntityModal from "./EntityModal";

function EntityModalPortal(props) {
  return <EntityModal {...props} />;
}
