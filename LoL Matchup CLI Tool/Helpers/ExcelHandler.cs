using ClosedXML.Excel;
using LoL_Matchup_CLI_Tool.Props;
using System.Collections.Concurrent;

#pragma warning disable IDE0063, IDE0290 // Fuck you IDE let me do my thing

namespace LoL_Matchup_CLI_Tool.Helpers
{
    class ExcelHandler
    {
        private readonly string[] MyChamps;
        private readonly HashSet<string> LineChamps;
        private readonly ConcurrentBag<Matchup> Matchups;

        public ExcelHandler(string[] myChamps, HashSet<string> lineChamps, ConcurrentBag<Matchup> matchups)
        {
            MyChamps = myChamps;
            LineChamps = lineChamps;
            Matchups = matchups;
        }

        public void CreateExcel(string path)
        {
            if (!path.EndsWith(".xlsx"))
                path += ".xlsx";

            using (var workbook = new XLWorkbook())
            {
                var worksheet = workbook.Worksheets.Add("Matchups");

                // Header row
                worksheet.Cell(2, 1).Value = "Champion Against";

                for (int i = 2; i < MyChamps.Length + 2; i++)
                {
                    worksheet.Cell(1, i).Value = MyChamps[i - 2];
                }

                List<ChampionMatchup> championMatchupList = [];
                string[] sortedChampions = LineChamps.OrderBy(x => x).ToArray(); // Sort Alphabetically

                for (int i = 0; i < sortedChampions.Length; i++)
                {
                    string curChamp = sortedChampions[i];
                    Matchup[] matchupsAgainst = Matchups.Where(x => x.ChampAgainst == curChamp).ToArray();

                    ChampionMatchup cm = new()
                    {
                        ChampionName = curChamp,
                        Ratings = MyChamps.Select(myChamp =>
                        {
                            var match = matchupsAgainst.FirstOrDefault(m => m.ChampPlaying == myChamp);
                            return match?.Rating ?? "N/A";
                        }).ToList()
                    };

                    championMatchupList.Add(cm);
                }

                for (int i = 2; i < MyChamps.Length + 2; i++)
                {
                    worksheet.Cell(1, i).Value = $"MyChamp#{i - 1}";
                }

                for (int i = 2; i < championMatchupList.Count + 3; ++i)
                {
                    if (i != 2)
                    {
                        worksheet.Cell(i, 1).Value = championMatchupList[i - 3].ChampionName;
                    }

                    for (int j = 2; j < MyChamps.Length + 2; ++j)
                    {
                        if (i == 2)
                        {
                            worksheet.Cell(i, j).Value = MyChamps[j - 2];
                        }
                        else
                        {
                            worksheet.Cell(i, j).Value = championMatchupList[i - 3].Ratings[j - 2];
                        }
                    }
                }
                AddStyleToCells(worksheet);

                // Auto fit and save
                worksheet.Columns().AdjustToContents();
                worksheet.SheetView.FreezeRows(2);
                workbook.SaveAs(path);

                Console.WriteLine($"Excel saved to : \n'{Path.GetFullPath(path)}'");
            }
        }

        private static void AddStyleToCells(IXLWorksheet worksheet)
        {
            IXLCell lastUsedCell = worksheet.LastCellUsed();

            int column = lastUsedCell.Address.ColumnNumber;
            int row = lastUsedCell.Address.RowNumber;

            for (int i = 1; i < row + 1; ++i)
            {
                for (int j = 1; j < column + 1; ++j)
                {
                    IXLCell currCell = worksheet.Cell(i, j);

                    switch (currCell.Value.ToString())
                    {
                        case "-":
                            currCell.Style.Fill.BackgroundColor = XLColor.RedNcs;
                            break;
                        case "+":
                            currCell.Style.Fill.BackgroundColor = XLColor.GreenYellow;
                            break;
                        case "S":
                            currCell.Style.Fill.BackgroundColor = XLColor.Yellow;
                            break;
                        case "D":
                            currCell.Style.Fill.BackgroundColor = XLColor.Green;
                            break;
                        case "D+":
                            currCell.Style.Fill.BackgroundColor = XLColor.Blue;
                            break;
                        case "UD":
                            currCell.Style.Fill.BackgroundColor = XLColor.Purple;
                            break;
                        case "N/A":
                            currCell.Style.Fill.BackgroundColor = XLColor.Black;
                            break;
                        default:
                            break;
                    }
                    currCell.Style.Border.OutsideBorder = XLBorderStyleValues.Thin;
                    currCell.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;
                }
            }
        }
    }
}
