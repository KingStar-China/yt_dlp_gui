using YtDlpGui.Core;

namespace YtDlpGui.Core.Tests;

public sealed class TransferStateMachineTests
{
    [Fact]
    public void SuccessfulSniffAndDownload_ReturnsToReadyState()
    {
        var state = new TransferStateMachine();

        state.BeginSniff();
        Assert.True(state.IsBusy);
        Assert.True(state.CanCancel);

        state.CompleteSniff(hasFormats: true);
        Assert.Equal(TransferState.ReadyToDownload, state.State);
        Assert.Equal("开始下载", state.PrimaryButtonText);

        state.BeginDownload();
        state.CompleteDownload();
        Assert.Equal(TransferState.ReadyToDownload, state.State);
    }

    [Fact]
    public void FailedSniff_ReturnsToIdle()
    {
        var state = new TransferStateMachine();
        state.BeginSniff();
        state.CompleteSniff(hasFormats: false);
        Assert.Equal(TransferState.Idle, state.State);
    }

    [Fact]
    public void DownloadBeforeSniff_IsRejected()
    {
        var state = new TransferStateMachine();
        Assert.Throws<InvalidOperationException>(state.BeginDownload);
    }

    [Fact]
    public void Update_PreservesReadyStateWhenFormatsExist()
    {
        var state = new TransferStateMachine();
        state.BeginSniff();
        state.CompleteSniff(hasFormats: true);
        state.BeginUpdate();
        state.CompleteUpdate(hasFormats: true);
        Assert.Equal(TransferState.ReadyToDownload, state.State);
    }
}
