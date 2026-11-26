"use client";

import type { NBAPlayerSeasonStats } from "@macfax/core/types/nba";
import { getBPRTier, fmtSigned } from "@macfax/core/lib/bprTiers";
import { getBprTier } from "@macfax/core/lib/nba-outlook-helpers";
import type { RatingScale } from "@macfax/core/types/nba";
import { BPRConfidenceBadge } from "./BPRConfidenceBadge";
import { clsx } from "clsx";
import Image from "next/image";
import Link from "next/link";

interface Props {
  player: NBAPlayerSeasonStats;
  /** Career-level aggregates from NBAPlayer — pass if available */
  peakBpr?: number | null;
  careerBpr?: number | null;
  className?: string;
}

export function PlayerScoutingCard({ player, peakBpr, careerBpr, className }: Props) {
  const tier = getBPRTier(player.wins_added, player.rating_scale);
  const headshotUrl = player.player_id
    ? `https://cdn.nba.com/headshots/nba/latest/1040x760/${player.player_id}.png`
    : null;

  return (
    <div
      className={clsx(
        "bg-slate-900 border border-slate-700 rounded-xl overflow-hidden font-mono",
        className,
      )}
    >
      {/* Header — player identity */}
      <div className="flex items-center gap-4 px-5 py-4 border-b border-slate-700 bg-slate-800/60">
        {headshotUrl && (
          <div className="w-14 h-14 rounded-full overflow-hidden bg-slate-700 flex-shrink-0">
            <Image
              src={headshotUrl}
              alt={player.player_name ?? ""}
              width={56}
              height={56}
              className="object-cover w-full h-full"
              onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
            />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <h2 className="text-slate-100 text-lg font-semibold truncate leading-tight">
            {player.player_name ?? "Unknown"}
          </h2>
          <div className="flex items-center gap-2 mt-0.5">
            {player.team_name && (
              <Link
                href={`/nba/team/${player.team_slug}`}
                className="text-xs text-slate-400 hover:text-teal-400 transition-colors"
              >
                {player.team_name}
              </Link>
            )}
            {player.season_display && (
              <span className="text-xs text-slate-600">· {player.season_display}</span>
            )}
            <span className="text-xs text-slate-600">
              · {player.gp ?? "—"} GP · {player.mpg?.toFixed(1) ?? "—"} MPG
            </span>
          </div>
        </div>
      </div>

      {/* Headline — Wins Added */}
      <div className="px-5 py-5 border-b border-slate-700/60">
        <div className="text-xs uppercase tracking-widest text-slate-500 mb-1">Wins Added</div>
        <div className="flex items-baseline gap-3">
          <span className={clsx("text-5xl font-bold tabular-nums", tier.color)}>
            {fmtSigned(player.wins_added, 1)}
          </span>
          <span className={clsx("text-sm px-2 py-0.5 rounded-md", tier.bgColor, tier.color)}>
            {tier.label}
          </span>
        </div>
        <p className="text-xs text-slate-500 mt-2">
          Worth {fmtSigned(player.wins_added, 1)} wins above a replacement-level player
        </p>
      </div>

      {/* BPR split — replacement-adjusted */}
      <div className="grid grid-cols-3 divide-x divide-slate-700/60 border-b border-slate-700/60">
        <BPRCell
          label="MPR (adj)"
          value={player.bpr_replacement_adjusted}
          tierValue={player.bpr}
          scale={player.rating_scale}
          tooltip="MPR replacement-adjusted — 0 = replacement level"
          primary
        />
        <BPRCell
          label="Off MPR"
          value={player.obpr_replacement_adjusted}
          tierValue={player.obpr}
          scale={player.rating_scale}
          tooltip="Offensive MPR replacement-adjusted"
        />
        <BPRCell
          label="Def MPR"
          value={player.dbpr_replacement_adjusted}
          tierValue={player.dbpr}
          scale={player.rating_scale}
          tooltip="Defensive MPR replacement-adjusted"
        />
      </div>

      {/* Career / Peak */}
      <div className="grid grid-cols-2 divide-x divide-slate-700/60 border-b border-slate-700/60">
        <BPRCell
          label="Career MPR"
          value={careerBpr ?? null}
          scale={player.rating_scale}
          tooltip="Minutes-weighted career average MPR (qualifying seasons ≥500 min)"
          small
        />
        <BPRCell
          label="Peak MPR"
          value={peakBpr ?? null}
          scale={player.rating_scale}
          tooltip="Best single-season MPR (qualifying seasons ≥500 min)"
          small
        />
      </div>

      {/* Raw stored BPR — footnote */}
      <div className="px-5 py-3 text-xs text-slate-600 flex items-center gap-4">
        <span>MPR (raw): {fmtSigned(player.bpr, 2)}</span>
        <span>O-MPR: {fmtSigned(player.obpr, 2)}</span>
        <span>D-MPR: {fmtSigned(player.dbpr, 2)}</span>
        <BPRConfidenceBadge
          league="nba"
          source="rapm"
          sample={(player.mpg ?? 0) * (player.gp ?? 0)}
          compact
        />
        {player.nba_archetype && (
          <span className="ml-auto capitalize text-slate-500">{player.nba_archetype.replace(/_/g, " ")}</span>
        )}
        {player.bpr_last_updated && (
          <span
            className="text-slate-600"
            title="When this rating was last recomputed. Ratings change when new games are played or the model version is updated."
          >
            upd {new Date(player.bpr_last_updated).toLocaleDateString()}
          </span>
        )}
      </div>
    </div>
  );
}

/**
 * A BPR value cell, coloured by the BPR tiers (getBprTier) of the underlying, unadjusted rating
 * (`tierValue`, default `value`) on the row's scale (task 5.10).
 */
function BPRCell({
  label,
  value,
  tierValue,
  scale,
  tooltip,
  primary = false,
  small = false,
}: {
  label: string;
  value: number | null | undefined;
  tierValue?: number | null;
  scale?: RatingScale;
  tooltip?: string;
  primary?: boolean;
  small?: boolean;
}) {
  const tier = getBprTier(tierValue !== undefined ? tierValue : value, scale);
  return (
    <div className="px-4 py-3 flex flex-col gap-0.5" title={tooltip}>
      <span className="text-xs uppercase tracking-wider text-slate-500">{label}</span>
      <span
        className={clsx(
          "tabular-nums font-semibold",
          primary ? "text-2xl" : small ? "text-base" : "text-xl",
          tier.className,
        )}
      >
        {fmtSigned(value, 2)}
      </span>
    </div>
  );
}
