using YtDlpGui.Core;

namespace YtDlpGui.Core.Tests;

public sealed class BilibiliDirectParserTests
{
    private readonly BilibiliDirectParser _parser = new();

    [Fact]
    public void Parse_SelectsPreferredCodecAndBestAacAudio()
    {
        const string playInfo = """
            {
              "data": {
                "dash": {
                  "video": [
                    {"baseUrl":"https://cdn.example/1080-av1","height":1080,"codecs":"av01.0.08M","frameRate":"60","bandwidth":6000000,"size":200000000},
                    {"base_url":"https://cdn.example/1080-h264","height":1080,"codecs":"avc1.640028","frame_rate":"30","bandwidth":4000000,"size":150000000},
                    {"baseUrl":"https://cdn.example/720-h264","height":720,"codecs":"avc1.64001F","frameRate":"30","bandwidth":2000000,"size":80000000}
                  ],
                  "audio": [
                    {"baseUrl":"https://cdn.example/audio-aac-low","codecs":"mp4a.40.2","bandwidth":64000,"size":5000000},
                    {"baseUrl":"https://cdn.example/audio-aac-high","codecs":"mp4a.40.2","bandwidth":128000,"size":10000000},
                    {"baseUrl":"https://cdn.example/audio-opus","codecs":"opus","bandwidth":160000,"size":12000000}
                  ]
                }
              }
            }
            """;
        const string initialState = """
            {"videoData":{"title":"A:B Video"}}
            """;

        var formats = _parser.Parse(playInfo, initialState, "https://www.bilibili.com/video/BV1", "test-agent");

        Assert.Equal(3, formats.Count);
        Assert.Equal("bili-direct-video:1", formats[0].Id);
        Assert.StartsWith("1080p/H.264/30fps", formats[0].Label);
        Assert.Equal("https://cdn.example/1080-h264", formats[0].DirectPayload?.VideoUrl);
        Assert.Equal("https://cdn.example/audio-aac-high", formats[0].DirectPayload?.AudioUrl);
        Assert.Equal("bili-direct-video:2", formats[1].Id);
        Assert.Equal(MediaKind.Audio, formats[2].Kind);
        Assert.Equal("https://cdn.example/audio-aac-high", formats[2].DirectPayload?.AudioUrl);
        Assert.Equal("A:B Video", formats[2].DirectPayload?.Title);
    }

    [Fact]
    public void Parse_ReturnsEmptyWhenDashDataIsMissing()
    {
        var formats = _parser.Parse("{\"data\":{}}", null, "https://www.bilibili.com/video/BV1", "test-agent");
        Assert.Empty(formats);
    }

    [Fact]
    public void DirectVideoNeedsFfmpegButDirectAudioDoesNot()
    {
        var payload = new DirectMediaPayload("title", "https://bilibili.com", "agent", "https://video", "https://audio");
        var video = new MediaFormat("video", "1080p/H.264", MediaKind.Video, DirectPayload: payload);
        var audio = new MediaFormat("audio", "音频/AAC", MediaKind.Audio, DirectPayload: payload);

        Assert.True(YtDlpCommandBuilder.NeedsFfmpeg(video));
        Assert.False(YtDlpCommandBuilder.NeedsFfmpeg(audio));
    }
}
