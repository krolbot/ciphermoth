import { Box, Stack, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";

import { getPasswordStrength } from "../../lib/passwordStrength";

const SEGMENTS = [0, 1, 2, 3, 4];

const StrengthBar = ({ password }) => {
  const { t } = useTranslation();
  const strength = getPasswordStrength(password);
  if (!strength) return null;

  return (
    <Box>
      <Stack direction="row" spacing={0.5} sx={{ mb: 0.75 }}>
        {SEGMENTS.map((i) => (
          <Box
            key={i}
            sx={{
              flex: 1,
              height: 4,
              borderRadius: 2,
              bgcolor: i <= strength.level ? strength.color : "grey.200",
              transition: "background-color 0.2s",
            }}
          />
        ))}
      </Stack>
      <Typography variant="caption" sx={{ color: strength.color, fontWeight: 600 }}>
        {t(strength.labelKey)}
        {strength.recommend && ` — ${t("strength.recommendation")}`}
      </Typography>
    </Box>
  );
};

export default StrengthBar;
