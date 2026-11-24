import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, BILLING } from "@/lib/api";
import { BuyCreditsDialog } from "@/components/buy-credits-dialog";
import { WaitlistDialog } from "@/components/waitlist-dialog";

const CreditsContext = createContext(null);

export function useCredits() {
    return useContext(CreditsContext);
}

export function CreditsProvider({ children }) {
    const [me, setMe] = useState(null);
    const [open, setOpen] = useState(false);
    const [reason, setReason] = useState(null);
    const [premiumOpen, setPremiumOpen] = useState(false);
    const openPremium = useCallback(() => { setOpen(false); setPremiumOpen(true); }, []);

    const refresh = useCallback(async () => {
        try {
            setMe(await api("/me", undefined, { base: BILLING }));
        }
        catch { }
    }, []);

    const openBuy = useCallback((why = null) => {
        setReason(why);
        setOpen(true);
    }, []);

    useEffect(() => {
        refresh();
        const onChange = () => refresh();
        const onOut = () => { refresh(); openBuy("You're out of credits. Pick a pack to keep going."); };
        window.addEventListener("dt:credits-changed", onChange);
        window.addEventListener("dt:out-of-credits", onOut);
        return () => {
            window.removeEventListener("dt:credits-changed", onChange);
            window.removeEventListener("dt:out-of-credits", onOut);
        };
    }, [refresh, openBuy]);

    return (<CreditsContext.Provider value={{ me, credits: me?.credits ?? null, refresh, openBuy, openPremium }}>
      {children}
      <BuyCreditsDialog open={open} reason={reason} me={me} onClose={() => setOpen(false)} onPaid={refresh} onPremium={openPremium}/>
      <WaitlistDialog open={premiumOpen} onClose={() => setPremiumOpen(false)}/>
    </CreditsContext.Provider>);
}
