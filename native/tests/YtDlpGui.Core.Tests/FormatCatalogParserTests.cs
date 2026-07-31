using YtDlpGui.Core;

namespace YtDlpGui.Core.Tests;

public sealed class FormatCatalogParserTests
{
    private readonly FormatCatalogParser _parser = new();

    [Fact]
    public void Parse_SelectsPreferredVideoPerResolutionAndBestAacAudio()
    {
        const string json = """
            {
              "formats": [
                {"format_id":"399","height":1080,"vcodec":"av01.0.08M","acodec":"none","fps":60,"tbr":6000,"filesize":200000000},
                {"format_id":"137","height":1080,"vcodec":"avc1.640028","acodec":"none","fps":30,"tbr":4000,"filesize":150000000},
                {"format_id":"22","height":720,"vcodec":"avc1.64001F","acodec":"mp4a.40.2","fps":30,"tbr":2000,"filesize":80000000},
                {"format_id":"140","vcodec":"none","acodec":"mp4a.40.2","ext":"m4a","tbr":129,"filesize":12000000},
                {"format_id":"139","vcodec":"none","acodec":"mp4a.40.5","ext":"m4a","tbr":48,"filesize":5000000},
                {"format_id":"251","vcodec":"none","acodec":"opus","ext":"webm","tbr":160,"filesize":14000000}
              ],
              "subtitles": {"zh-Hans":[{"ext":"vtt"},{"ext":"srt"}]},
              "automatic_captions": {"en":[{"ext":"vtt"}]}
            }
            """;

        var formats = _parser.Parse(json, isPlaylist: false);

        Assert.Equal(5, formats.Count);
        Assert.Equal("137", formats[0].Id);
        Assert.StartsWith("1080p/H.264/30fps", formats[0].Label);
        Assert.Equal("22", formats[1].Id);
        Assert.True(formats[1].HasAudio);
        Assert.Equal("140", formats[2].Id);
        Assert.Equal(MediaKind.Audio, formats[2].Kind);
        Assert.Equal("subtitle:zh-Hans:manual", formats[3].Id);
        Assert.Equal("subtitle:en:auto", formats[4].Id);
    }

    [Fact]
    public void Parse_UsesLastJsonLineWhenToolWritesLeadingNoise()
    {
        const string output = "warning line\n{\"formats\":[{\"format_id\":\"22\",\"height\":720,\"vcodec\":\"avc1\",\"acodec\":\"mp4a\"}]}";

        var formats = _parser.Parse(output, isPlaylist: false);

        Assert.Single(formats);
        Assert.Equal("22", formats[0].Id);
    }

    [Fact]
    public void Parse_BuildsBothPlaylistModes()
    {
        const string json = """
            {
              "title":"My:Playlist",
              "entries":[{"id":"one"},{"id":"two"},null]
            }
            """;

        var formats = _parser.Parse(json, isPlaylist: true);

        Assert.Equal(2, formats.Count);
        Assert.All(formats, format => Assert.Equal(MediaKind.Playlist, format.Kind));
        Assert.Equal(2, formats[0].PlaylistCount);
        Assert.Equal("My:Playlist", formats[0].PlaylistTitle);
    }

    [Fact]
    public void Parse_ThrowsUsefulErrorForInvalidOutput()
    {
        var error = Assert.Throws<FormatException>(() => _parser.Parse("not json", isPlaylist: false));
        Assert.Contains("JSON", error.Message);
    }
}
