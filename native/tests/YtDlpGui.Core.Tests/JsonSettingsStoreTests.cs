using YtDlpGui.Core;
using YtDlpGui.Infrastructure;

namespace YtDlpGui.Core.Tests;

public sealed class JsonSettingsStoreTests
{
    [Fact]
    public async Task LoadAsync_UsesAndCreatesApplicationDownloadsByDefault()
    {
        var testRoot = CreateTestRoot();

        try
        {
            var applicationDirectory = Path.Combine(testRoot, "app");
            Directory.CreateDirectory(applicationDirectory);
            var store = new JsonSettingsStore(
                Path.Combine(testRoot, "settings", "settings.json"),
                applicationDirectory);

            var settings = await store.LoadAsync();

            var expected = Path.Combine(applicationDirectory, "Downloads");
            Assert.Equal(expected, settings.OutputDirectory);
            Assert.True(Directory.Exists(expected));
        }
        finally
        {
            Directory.Delete(testRoot, recursive: true);
        }
    }

    [Fact]
    public async Task LoadAsync_PreservesAnExistingUserSelectedDirectory()
    {
        var testRoot = CreateTestRoot();

        try
        {
            var applicationDirectory = Path.Combine(testRoot, "app");
            var selectedDirectory = Path.Combine(testRoot, "selected");
            Directory.CreateDirectory(applicationDirectory);
            Directory.CreateDirectory(selectedDirectory);
            var store = new JsonSettingsStore(
                Path.Combine(testRoot, "settings", "settings.json"),
                applicationDirectory);
            await store.SaveAsync(new AppSettings(selectedDirectory));

            var settings = await store.LoadAsync();

            Assert.Equal(selectedDirectory, settings.OutputDirectory);
            Assert.False(Directory.Exists(Path.Combine(applicationDirectory, "Downloads")));
        }
        finally
        {
            Directory.Delete(testRoot, recursive: true);
        }
    }

    private static string CreateTestRoot()
    {
        var directory = Path.Combine(
            Path.GetTempPath(),
            "YtDlpGui.Tests",
            Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        return directory;
    }
}
