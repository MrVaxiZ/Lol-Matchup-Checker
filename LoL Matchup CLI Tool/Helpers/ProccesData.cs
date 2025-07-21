using LoL_Matchup_CLI_Tool.Props;

namespace LoL_Matchup_CLI_Tool.Helpers
{
    class ProccesData
    {
        private readonly Matchup Matchup;

        public ProccesData(Matchup matchup)
        {
            Matchup = matchup;
        }

        internal string? GetMatchupRating()
        {
            if (Matchup.WinRate < 49.0)
            {
                return "-";
            }
            else if (Matchup.WinRate >= 49.0 && Matchup.WinRate <= 51.0)
            {
                return "S";
            }
            else if (Matchup.WinRate > 51.0 && Matchup.WinRate < 53.0)
            {
                return "+";
            }
            else if (Matchup.WinRate >= 53.0 && Matchup.WinRate < 55.0)
            {
                return "D";
            }
            else if (Matchup.WinRate >= 55.0 && Matchup.WinRate < 60.0)
            {
                return "D+";
            }
            else if (Matchup.WinRate >= 60.0)
            {
                return "UD";
            }
            else
            {
                return null;
            }
        }
    }
}
