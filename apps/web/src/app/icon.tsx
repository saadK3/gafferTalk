import { ImageResponse } from "next/og";

export const size = { width: 64, height: 64 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#101d2a",
        color: "#f5f3ec",
        fontFamily: "Arial, sans-serif",
        fontSize: 29,
        fontWeight: 900,
        letterSpacing: -3,
      }}
    >
      GT<span style={{ color: "#d8296a" }}>.</span>
    </div>,
    size,
  );
}
