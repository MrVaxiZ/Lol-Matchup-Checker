namespace GetTopMachupsForGivenChamps.Props
{
    public class Matchup
    {
        public string ChampAgainst { get; set; } = string.Empty;
        public string ChampPlaying { get; set; } = string.Empty;
        public uint Matches { get; set; } = uint.MinValue;
        public double WinRate { get; set; } = double.NaN;
        public string? Rating { get; set; } = null;
    }
}
