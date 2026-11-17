import { LEGAL_DISCLAIMER } from "@/lib/disclaimer";
import WarningIcon from "@/components/WarningIcon";

/**
 * 全局预埋免责声明：所有法律输出页面（问答/意见书/图谱/合同/类案/法庭）统一挂载。
 * 图标用内联 SVG（不使用 emoji），跟随文字色随主题切换。
 */
export default function LegalDisclaimer({ className = "" }: { className?: string }) {
  return (
    <p className={`disclaimer ${className}`} role="note">
      <WarningIcon className="mr-1 inline-block align-[-2px]" />
      {LEGAL_DISCLAIMER}
    </p>
  );
}
