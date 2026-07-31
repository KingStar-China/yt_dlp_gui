namespace YtDlpGui.Core;

public sealed class TransferStateMachine
{
    public TransferState State { get; private set; } = TransferState.Idle;

    public bool IsBusy => State is TransferState.Sniffing or TransferState.Downloading or TransferState.Updating;

    public bool CanCancel => State is TransferState.Sniffing or TransferState.Downloading;

    public string PrimaryButtonText => State switch
    {
        TransferState.Sniffing => "正在嗅探",
        TransferState.ReadyToDownload => "开始下载",
        TransferState.Downloading => "正在下载",
        _ => "开始嗅探",
    };

    public void BeginSniff()
    {
        Ensure(State is TransferState.Idle or TransferState.ReadyToDownload, "当前状态不能开始嗅探。");
        State = TransferState.Sniffing;
    }

    public void CompleteSniff(bool hasFormats)
    {
        Ensure(State == TransferState.Sniffing, "当前没有正在进行的嗅探。");
        State = hasFormats ? TransferState.ReadyToDownload : TransferState.Idle;
    }

    public void BeginDownload()
    {
        Ensure(State == TransferState.ReadyToDownload, "当前状态不能开始下载。");
        State = TransferState.Downloading;
    }

    public void CompleteDownload() => State = State == TransferState.Downloading
        ? TransferState.ReadyToDownload
        : throw new InvalidOperationException("当前没有正在进行的下载。");

    public void BeginUpdate()
    {
        Ensure(!IsBusy, "传输任务进行中，不能更新 yt-dlp。");
        State = TransferState.Updating;
    }

    public void CompleteUpdate(bool hasFormats) => State = State == TransferState.Updating
        ? hasFormats ? TransferState.ReadyToDownload : TransferState.Idle
        : throw new InvalidOperationException("当前没有正在进行的更新。");

    public void Reset() => State = TransferState.Idle;

    private static void Ensure(bool condition, string message)
    {
        if (!condition)
        {
            throw new InvalidOperationException(message);
        }
    }
}
