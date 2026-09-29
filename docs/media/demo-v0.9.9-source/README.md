# v0.9.9 demo source captures

These 17 PNGs are actual browser states from an isolated synthetic Pivotglass case. The chapter manifest maps each capture to its narration and exact speech duration. They are edited scene holds, not a continuous recording or evidence of a live threat investigation.

## Production method

1. Capture the offline case at the normal 1265 × 712 browser viewport. Include the report’s two export buttons and the named Nightgrid presentation.
2. Generate the 17 narration paragraphs with Descript’s Jesse stock neural voice. Real paragraph breaks are necessary: one long speech block exceeded Descript’s synthesis limit.
3. Export and decode the actual speech; agent success messages alone are insufficient. Align each matching screen to the generated chapter duration in the manifest.
4. Assemble H.264 video with FFmpeg at 25 fps, padding the UI to 1280 × 720 and adding a 96-pixel caption band below it. Copy the generated AAC speech without substituting operating-system speech.
5. Use Descript’s audio-aligned transcript ticks for external WebVTT captions. Keep all spoken words, merge very short adjacent cues within chapters, and wrap to two lines. Alignment is approximately five-second granularity, not word-level timing.
6. Decode the complete MP4, check chapter frames, and verify captions and playback in the HTML player. The narration can be extracted from the MP4 for a future edit; separate duplicate audio is not required.

The final candidate is 300.16 seconds. No enrichment or investigative LLM call ran during the capture. The neural narration is presentation, not analytical authority. Voice quality requires owner listening review before release acceptance.
