using YtDlpGui.Core;

namespace YtDlpGui.Core.Tests;

public sealed class FileNameSanitizerTests
{
    [Theory]
    [InlineData("hello:world?.mp4", "hello_world_.mp4")]
    [InlineData("CON", "_CON")]
    [InlineData(" name. ", "name")]
    [InlineData("", "video")]
    public void Sanitize_ProducesWindowsSafeNames(string input, string expected) =>
        Assert.Equal(expected, FileNameSanitizer.Sanitize(input));

    [Theory]
    [InlineData(500, "500B")]
    [InlineData(1536, "1.5KB")]
    [InlineData(1572864, "1.5MB")]
    [InlineData(1610612736, "1.5GB")]
    public void FormatSize_UsesReadableBinaryUnits(long input, string expected) =>
        Assert.Equal(expected, FileNameSanitizer.FormatSize(input));
}
