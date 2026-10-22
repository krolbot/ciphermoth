import { Box, Button, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import { useTranslation } from "react-i18next";

import MothIcon from "../MothIcon";
import { GLOW } from "../../lib/brand";

const EmptyVault = ({ onAdd }) => {
  const { t } = useTranslation();

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        py: 10,
        gap: 2,
        bgcolor: "background.paper",
        borderRadius: 3,
        border: "1px dashed",
        borderColor: "divider",
      }}
    >
      <Box
        sx={{
          width: 96,
          height: 96,
          mb: 1,
          color: "text.primary",
          filter: `drop-shadow(0 0 16px color-mix(in srgb, ${GLOW} 40%, transparent))`,
        }}
      >
        <MothIcon width="100%" height="100%" style={{ display: "block", overflow: "visible" }} />
      </Box>
      <Typography variant="h6" sx={{ fontWeight: 600 }}>
        {t("vault.emptyTitle")}
      </Typography>
      <Typography
        variant="body2"
        sx={{ color: "text.secondary", textAlign: "center", maxWidth: 320 }}
      >
        {t("vault.emptyDescription")}
      </Typography>
      <Button variant="contained" startIcon={<AddIcon />} onClick={onAdd} sx={{ mt: 1 }}>
        {t("vault.addFirstPassword")}
      </Button>
    </Box>
  );
};

export default EmptyVault;
