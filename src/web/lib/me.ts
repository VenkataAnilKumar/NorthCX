"use client";
import { useEffect, useState } from "react";
import { getMe, type Me } from "@/lib/api";

let cached: Promise<Me> | null = null;
export const resetMe = () => { cached = null; };

/** Who the server says we are. While unknown (or if the lookup fails) every action looks allowed and the server decides. */
export function useMe() {
  const [me, setMe] = useState<Me | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    (cached ??= getMe()).then((m) => live && setMe(m)).catch(() => { cached = null; if (live) setFailed(true); });
    return () => { live = false; };
  }, []);
  const can = (permission: string) => !me || me.permissions.includes(permission);
  // Names typed into forms are only trusted when the server has no authentication; otherwise the key's name is used.
  return { me, failed, can, askForName: !me || me.openMode };
}
