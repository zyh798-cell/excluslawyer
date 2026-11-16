import { LEGAL_DISCLAIMER } from "@/lib/disclaimer";

/**
 * 全局预埋免责声明：所有法律输出页面（问答/意见书/图谱/合同/类案/法庭）统一挂载。
 */
export default function LegalDisclaimer({ className = "" }: { className?: string }) {
  return (
    <p className={`disclaimer ${className}`} role="note">
      ⚠️ {LEGAL_DISCLAIMER}
    </p>
  );
}
