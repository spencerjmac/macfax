# Build this: “March isn't as mad as you think.”

One native Power BI scatter chart, built **in your browser**. Budget: 20–25 minutes. No DAX, relationships, or custom visuals.

**The story:** 17 of 21 tournament winners (81%) entered March in the top 10% of both offense and defense. Only 275 of 7,311 available team-seasons (3.8%) met both conditions. The interesting exception to demonstrate: **2014 Connecticut, offense #54, defense #12**.

Everything you need is in this folder. `preview.png` shows the intended design; it is a reference image, not a Power BI screenshot. `report_background.png` supplies the finished headline, legend, and footer. Put the actual interactive chart on top of that background.

1. **Import the data — minutes 0–3.** In [Power BI](https://app.powerbi.com), open **My workspace → New item → Semantic model → CSV → Upload file**, then choose `championship_blueprint.csv`. Select **Next**, check the preview, select **Next → Create a report**, name the model **Macfax Championship Blueprint**, and choose **Create**. Open the report in **Edit** mode. If Power BI creates suggested visuals, remove those before adding your scatter. This CSV is already cleaned and joined. The percentile and marker-size fields should be numeric.

   **If upload fails with `Invalid audience Uri 'https://graph.microsoft.com/'`, or you don't see CSV upload:** use the paste route to bypass the file-upload step. Choose **Create / New report → Paste or manually enter data**. Open `browser_paste.tsv` in your editor as plain text, press **Ctrl+A**, then **Ctrl+C**, and paste into the table with **Ctrl+V**. Turn on **Use first row as headers**, name the table **Blueprint**, and create the report. Choose **Edit** to enter the full report editor. This fallback has the **1,048 already-zoomed rows**, including all 21 winners, and is below the 512 KB paste limit; no row filters are needed for it. The full CSV contains the 7,311-row comparison set behind the headline. Avoid pasting the full CSV.

2. **Apply the design — minutes 3–6.** In report **Edit** mode, open **View → Theme**. If available, expand **Theme settings → Import theme** and choose `macfax_theme.json`; otherwise choose a dark theme and use the explicit chart colors below. Click the empty page, open **Format page → Canvas settings**, and select **Custom**, width **1600**, height **900**. Under **Canvas background**, add `report_background.png`, choose **Fit**, and set transparency to **0%**. Use Canvas background for the image. Choose **View → Fit to page** to see the complete layout. If image backgrounds are unavailable in your tenant, insert the image on the canvas, size it to 1600 × 900 at X 0 / Y 0, then send it to the back.

3. **Build the scatter — minutes 6–12.** Add the built-in **Scatter chart**. Drag the following columns into its field wells:

   | Power BI field well | CSV column | Setting |
   |---|---|---|
   | Values (called Details in some versions) | `season_team` | One unique team-season per dot |
   | X axis | `offense_percentile` | Average |
   | Y axis | `defense_percentile` | Average |
   | Legend | `result` | Keeps winners and other teams separate |
   | Size | `marker_size` | Average |
   | Tooltips | `season_team`, `offense_rank`, `defense_rank`, `adjusted_offense`, `adjusted_defense`, `title_note` | Use Min or Average for numbers; include the team-season name |

   **Keep `season_team` in Values/Details.** Without it, Power BI may collapse your teams into two bubbles. Do not put it in Legend.

   If you uploaded the full CSV, in **Filters on this visual**, add `offense_percentile` and set **is greater than or equal to 75**. Do the same for `defense_percentile`. You should now have **1,048 dots, including all 21 winners**. The paste fallback already contains exactly those rows. This zoom makes the gold dots readable. The headline's 3.8% still refers to the complete 7,311-row dataset, as stated on the background.

4. **Format the chart — minutes 12–20.** Under **Format visual → General → Properties**, set **X 60**, **Y 270**, **Width 1480**, **Height 545**. Then apply these settings:

   | Setting | Value |
   |---|---|
   | Visual background | 100% transparent / Off |
   | Title, border, shadow | Off |
   | Legend display | Off; the background already contains the legend |
   | X axis range | Minimum 75, maximum 101 |
   | Y axis range | Minimum 75, maximum 101 |
   | X axis title | `OFFENSE PERCENTILE · HIGHER IS BETTER` |
   | Y axis title | `DEFENSE PERCENTILE · HIGHER IS BETTER` |
   | Axis text | `#B4C1D3`, approximately 12–14 pt |
   | Gridlines | Off, or very faint `#243247` |
   | Other team-seasons color | `#4B5B70` |
   | Tournament winner color | `#F5C451` |
   | Data/category labels | Off |

   **Fix oversized bubbles first.** Open **Format visual → Visual → Markers** (some versions call this **Bubbles**), expand **Shape** if needed, and reduce the **Size** slider toward its minimum. If it uses a signed numeric scale, start at **−25**. Aim for gray dots about **3–4 pixels across** and gold dots about **10–12 pixels across**, adjusting by appearance at your final chart size. These are visual targets, not values to enter into a percentage or signed-size control. Keep `marker_size` in the Size field well so winners remain larger. The theme now also supplies a smaller default bubble size; existing manual formatting can override it.

   Set the two series colors explicitly under **Markers / Colors / Series** (the label varies by version); the theme alone may assign the two colors in the opposite order. `marker_size` gives winners extra visual emphasis; bubble area is not a basketball metric. If your version supports **Auto-fit markers**, turn it on.

   Open the **Analytics** pane and add an **X-axis constant line at 90** and a **Y-axis constant line at 90**. Use teal `#56D6CF`, dashed, thin, with labels on. Name them **Top 10% offense** and **Top 10% defense**. The region above and to the right of both lines is the championship concentration. Constant lines may instead appear under **Reference lines** in your formatting pane.

5. **Check and present — minutes 20–25.** Hover a gold dot and verify its name and national ranks appear. Hover **2014 Connecticut**, the gold dot near **(84.68, 96.82)**: it won with offense ranked #54. Compare it with the dense group of winners above both 90 lines. **Save** the report to your workspace as **Macfax — The Championship Blueprint**. Keep this as a single chart; the background headline already communicates the takeaway. Leave filters at the specified settings so the fixed headline statistics remain accurate.

Say this to the judges:

> “March Madness looks random. I used Macfax's pre-tournament ratings to map offense and defense within each season. Eighty-one percent of tournament winners came from a group containing just 3.8 percent of all team-seasons. But this gold dot is 2014 Connecticut: only the 54th-ranked offense. The pattern is strong, and the exceptions are why we watch.”

Data and interpretation:

- Source: local Macfax `TeamSeasonRatings`, exported November 12, 2026. Coverage is the 2005–2026 ending seasons, omitting the canceled 2020 tournament. There are 7,311 valid historical team snapshots and 21 on-court winners. No ratings were missing or discarded during export. Louisville's 2013 on-court win is included with its vacated-title note.
- X and Y use **pre-tournament** rows. Winner labels come from the final-season records, joined by team and season. Historical snapshots may have been reconstructed later; this is a descriptive comparison, not a live prediction backtest.
- Percentiles are recalculated within each season: `100 × (N − rank) / (N − 1)`, using competition ranks. Higher offense is better; lower adjusted defensive rating is better. Both plotted percentiles run upward toward better performance. A value of 95 means a team was approximately in that season's top 5%.
- The gray dots in the displayed zoom are teams in approximately the top quarter of **both** ratings, including teams that did not enter the tournament. The comparison behind the 3.8% headline uses **all available team-seasons**. These are team-seasons, not distinct programs. This does not imply that every team inside the box wins, or that teams outside it cannot win.
- `data_notes.json` contains exact counts and the four winners outside the 90/90 region. The background statistics are fixed for this complete export; adding slicers would require updating those labels.
- To refresh the export from the repository root: `backend/.venv/bin/python tools/export_powerbi_blueprint.py`. The script reads the database inside a read-only transaction and writes the CSV, paste fallback, and data notes. Regenerate the artwork if the counts change.

Microsoft references: [browser CSV upload](https://learn.microsoft.com/en-us/power-bi/connect-data/service-comma-separated-value-files), [paste-data fallback](https://learn.microsoft.com/en-us/power-bi/create-reports/service-quick-create-report), [scatter charts, unique point IDs, and reference lines](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualization-scatter), [themes](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-report-themes), [canvas sizing](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-report-display-settings), and [canvas backgrounds](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-visual-elements-for-reports). [NCAA tournament records](https://fs.ncaa.org.s3.amazonaws.com/Docs/stats/m_final4/Brackets.pdf) note Louisville's vacated 2013 appearance.
