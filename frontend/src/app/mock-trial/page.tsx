import type { Metadata } from "next";
import MockTrialView from "@/components/MockTrialView";

export const metadata: Metadata = {
  title: "模拟法庭 — EXCLUSLAWYER",
  description:
    "LangGraph 庭审状态机推演：诉状挂条、双视角对抗、举证质证、时效联动、模拟裁判。仅供法律推演，不具法律效力。",
};

export default function MockTrialPage() {
  return <MockTrialView />;
}
