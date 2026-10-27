import { useEffect, useState } from "react";
import { Button, Tooltip } from "@gravity-ui/uikit";
import { useTranslation } from "react-i18next";

import { generateTotp, totpRemaining } from "../../lib/totp";

const PERIOD = 30;

const TotpCell = ({ secret, onCopy }) => {
  const { t } = useTranslation();
  const [code, setCode] = useState("");
  const [remaining, setRemaining] = useState(PERIOD);
  const [invalid, setInvalid] = useState(false);

  useEffect(() => {
    let active = true;
    const tick = async () => {
      try {
        const next = await generateTotp(secret);
        if (!active) return;
        setCode(next);
        setInvalid(false);
      } catch {
        if (active) setInvalid(true);
      }
      if (active) setRemaining(totpRemaining(PERIOD));
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, [secret]);

  if (invalid) return <span className="cm-totp__error">{t("totp.invalid")}</span>;
  if (!code) return null;

  return (
    <Tooltip content={t("totp.copy")}>
      <Button
        type="button"
        view="flat-secondary"
        aria-label={t("totp.copy")}
        onClick={() => onCopy?.(code)}
        className="cm-totp"
      >
        <span className="cm-totp__code">
          {code.slice(0, 3)} {code.slice(3)}
        </span>
        <span
          className={`cm-totp__remaining${remaining <= 5 ? " cm-totp__remaining--urgent" : ""}`}
          aria-hidden="true"
        >
          {remaining}s
        </span>
      </Button>
    </Tooltip>
  );
};

export default TotpCell;
