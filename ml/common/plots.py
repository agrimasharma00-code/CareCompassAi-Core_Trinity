def save_history(rows, path):
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(); ax.plot([r["epoch"] for r in rows if r["phase"]=="train"],[r["loss"] for r in rows if r["phase"]=="train"],label="train loss"); ax.set_xlabel("epoch");ax.legend();fig.savefig(path,bbox_inches="tight");plt.close(fig)
