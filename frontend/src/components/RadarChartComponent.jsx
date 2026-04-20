import React from "react";
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis,
  ResponsiveContainer, Tooltip,
} from "recharts";

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const { subject, score } = payload[0].payload;
  return (
    <div style={{
      background: "#0c1420",
      border: "1px solid #1a2d45",
      borderRadius: 8,
      padding: "10px 14px",
    }}>
      <div style={{ fontFamily: "JetBrains Mono", fontSize: "0.7rem",
        color: "#5a7a99", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.08em" }}>
        {subject}
      </div>
      <div style={{ fontFamily: "JetBrains Mono", fontSize: "1.3rem",
        color: score >= 80 ? "#00e676" : score >= 60 ? "#ffab40" : "#ff5252", fontWeight: 600 }}>
        {score}<span style={{ fontSize: "0.75rem", color: "#2a4a6a" }}>/100</span>
      </div>
    </div>
  );
};

export default function RadarChartComponent({ data }) {
  if (!data) return null;

  const chartData = Object.entries(data)
    .filter(([, val]) => typeof val === "number")
    .map(([key, val]) => ({
      subject: key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()),
      score: val,
      fullMark: 100,
    }));

  if (!chartData.length) return null;

  return (
    <ResponsiveContainer width="100%" height="100%">
      <RadarChart cx="50%" cy="50%" outerRadius="68%" data={chartData}>
        <PolarGrid stroke="#1a2d45" strokeWidth={1} />
        <PolarAngleAxis
          dataKey="subject"
          tick={{ fill: "#5a7a99", fontSize: 10, fontFamily: "JetBrains Mono" }}
        />
        <Tooltip content={<CustomTooltip />} />
        <Radar
          name="Score"
          dataKey="score"
          stroke="#00d4ff"
          fill="#00d4ff"
          fillOpacity={0.12}
          strokeWidth={1.5}
          dot={{ r: 3, fill: "#00d4ff", strokeWidth: 0 }}
        />
      </RadarChart>
    </ResponsiveContainer>
  );
}