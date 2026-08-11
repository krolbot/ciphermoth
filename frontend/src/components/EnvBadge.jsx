import { Box, Chip, Tooltip } from "@mui/material";
import { useTranslation } from "react-i18next";

import { DEV_ACCENT, IS_DEV } from "../lib/appEnv";
import { GLOW, INK } from "../lib/brand";

const baseSx = {
  height: 22,
  fontFamily: "'Space Mono', monospace",
  fontSize: 10,
  letterSpacing: "0.12em",
  borderRadius: 1,
  cursor: "help",
  "& .MuiChip-label": { px: 0.9 },
};

const EnvBadge = () => {
  const { t } = useTranslation();

  return (
    <Tooltip arrow title={t(IS_DEV ? "environment.developmentTooltip" : "environment.liveTooltip")}>
      <Chip
        size="small"
        label={
          IS_DEV ? (
            t("environment.development")
          ) : (
            <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.6 }}>
              <Box
                component="span"
                sx={{
                  width: 5,
                  height: 5,
                  borderRadius: "50%",
                  bgcolor: GLOW,
                  boxShadow: `0 0 5px ${GLOW}`,
                }}
              />
              {t("environment.live")}
            </Box>
          )
        }
        variant={IS_DEV ? "filled" : "outlined"}
        aria-label={t(IS_DEV ? "environment.developmentAria" : "environment.liveAria")}
        sx={
          IS_DEV
            ? { ...baseSx, fontWeight: 700, bgcolor: DEV_ACCENT, color: INK }
            : {
                ...baseSx,
                color: GLOW,
                borderColor: `color-mix(in srgb, ${GLOW} 45%, transparent)`,
              }
        }
      />
    </Tooltip>
  );
};

export default EnvBadge;
