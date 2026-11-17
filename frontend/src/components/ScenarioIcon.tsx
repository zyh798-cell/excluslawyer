"use client";

import {
  Briefcase,
  Car,
  Coins,
  GraduationCap,
  Heart,
  House,
  MessageCircle,
  ShoppingBag,
  type LucideIcon,
} from "lucide-react";
import type { ScenarioIconName } from "@/config/scenarios";

/**
 * 场景图标集：统一内联 SVG（lucide 渲染为 <svg>，无 emoji、无位图）。
 * 与 config/scenarios.ts 的 ScenarioIconName 一一对应，新增图标只需在此登记。
 */
const ICONS: Record<ScenarioIconName, LucideIcon> = {
  home: House,
  briefcase: Briefcase,
  "shopping-bag": ShoppingBag,
  heart: Heart,
  car: Car,
  coins: Coins,
  "graduation-cap": GraduationCap,
  "message-circle": MessageCircle,
};

export default function ScenarioIcon({
  name,
  size = 20,
  className = "",
}: {
  name: ScenarioIconName;
  size?: number;
  className?: string;
}) {
  const Icon = ICONS[name] ?? MessageCircle;
  return <Icon size={size} className={className} aria-hidden="true" focusable="false" />;
}
