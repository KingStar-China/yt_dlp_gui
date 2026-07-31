using System.Text.Json;
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
            Assert.Equal(AppTheme.System, settings.Theme);
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
            await store.SaveAsync(new AppSettings(selectedDirectory, AppTheme.Dark));

            var settings = await store.LoadAsync();

            Assert.Equal(selectedDirectory, settings.OutputDirectory);
            Assert.Equal(AppTheme.Dark, settings.Theme);
            Assert.Contains(
                "\"theme\": \"Dark\"",
                await File.ReadAllTextAsync(Path.Combine(testRoot, "settings", "settings.json")));
            Assert.False(Directory.Exists(Path.Combine(applicationDirectory, "Downloads")));
        }
        finally
        {
            Directory.Delete(testRoot, recursive: true);
        }
    }

    [Fact]
    public async Task LoadAsync_DefaultsLegacySettingsToSystemTheme()
    {
        var testRoot = CreateTestRoot();

        try
        {
            var applicationDirectory = Path.Combine(testRoot, "app");
            var selectedDirectory = Path.Combine(testRoot, "selected");
            var settingsPath = Path.Combine(testRoot, "settings", "settings.json");
            Directory.CreateDirectory(applicationDirectory);
            Directory.CreateDirectory(selectedDirectory);
            Directory.CreateDirectory(Path.GetDirectoryName(settingsPath)!);
            await File.WriteAllTextAsync(
                settingsPath,
                JsonSerializer.Serialize(new { outputDirectory = selectedDirectory }));
            var store = new JsonSettingsStore(settingsPath, applicationDirectory);

            var settings = await store.LoadAsync();

            Assert.Equal(selectedDirectory, settings.OutputDirectory);
            Assert.Equal(AppTheme.System, settings.Theme);
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
