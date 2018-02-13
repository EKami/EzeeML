"""
This module contains callbacks used during training/validation phases.
"""
import os
import torch
import torch.optim.lr_scheduler as lr_scheduler
from tqdm import tqdm
from collections import OrderedDict


class TrainCallback:
    def on_epoch_begin(self, epoch, logs=None):
        pass

    def on_epoch_end(self, epoch, logs=None):
        pass

    def on_batch_begin(self, batch, logs=None):
        pass

    def on_batch_end(self, batch, logs=None):
        pass

    def on_train_begin(self, logs=None):
        pass

    def on_train_end(self, logs=None):
        pass


class TrainCallbackList(object):
    """Container abstracting a list of callbacks.
    Args:
        callbacks: List of `Callback` instances.
        queue_length: Queue length for keeping
            running statistics over callback execution time.
    """

    def __init__(self, callbacks=None, queue_length=10):
        callbacks = callbacks or []
        self.callbacks = [c for c in callbacks]
        self.queue_length = queue_length

    def append(self, callback):
        assert isinstance(callback, TrainCallback), f"Your callback is not an instance of TrainCallback: {callback}"
        self.callbacks.append(callback)

    def on_epoch_begin(self, epoch, logs=None):
        """Called at the start of an epoch.
        Args:
            epoch: integer, index of epoch (starts at 1).
            logs: dictionary of logs.
        """
        logs = logs or {}
        for callback in self.callbacks:
            callback.on_epoch_begin(epoch, logs)

    def on_epoch_end(self, epoch, logs=None):
        """Called at the end of an epoch.
        Args:
            epoch: integer, index of epoch.
            logs: dictionary of logs.
        """
        logs = logs or {}
        for callback in self.callbacks:
            callback.on_epoch_end(epoch, logs)

    def on_batch_begin(self, batch, logs=None):
        """Called right before processing a batch.
        Args:
            batch: integer, index of batch within the current epoch.
            logs: dictionary of logs.
        """
        logs = logs or {}
        for callback in self.callbacks:
            callback.on_batch_begin(batch, logs)

    def on_batch_end(self, batch, logs=None):
        """Called at the end of a batch.
        Args:
            batch: integer, index of batch within the current epoch.
            logs: dictionary of logs.
        """
        logs = logs or {}
        for callback in self.callbacks:
            callback.on_batch_end(batch, logs)

    def on_train_begin(self, logs=None):
        """Called at the beginning of training.
        Args:
            logs: dictionary of logs.
        """
        logs = logs or {}
        for callback in self.callbacks:
            callback.on_train_begin(logs)

    def on_train_end(self, logs=None):
        """Called at the end of training.
        Args:
            logs: dictionary of logs.
        """
        logs = logs or {}
        for callback in self.callbacks:
            callback.on_train_end(logs)

    def __iter__(self):
        return iter(self.callbacks)


class TQDM(TrainCallback):
    def __init__(self):
        super().__init__()
        self.train_pbar = None
        self.val_pbar = None
        self.total_epochs = 0
        self.train_loader_len = 0
        self.val_loader_len = 0

    def on_epoch_begin(self, epoch, logs=None):
        step = logs["step"]
        if step == 'training':
            self.train_pbar = tqdm(total=self.train_loader_len,
                                   desc="Epochs {}/{}".format(epoch, self.total_epochs),
                                   bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{remaining}{postfix}]'
                                   )
        elif step == 'validation':
            self.val_pbar = tqdm(total=self.val_loader_len, desc="Validating", leave=False)

    def on_epoch_end(self, epoch, logs=None):
        step = logs["step"]

        if step == 'training':
            self.train_pbar.close()
            train_logs = logs['epoch_logs']
            train_metrics = logs['metrics_logs']
            print(*["{}={:03f}".format(k, v) for k, v in train_logs.items()], end=' ')

            print("| Train metrics:", end=' ')
            print(*["{}={:03f}".format(k, v) for k, v in train_metrics.items()])
        elif step == 'validation':
            self.val_pbar.close()
            val_logs = logs.get('epoch_logs')
            if val_logs:
                print(*["{}={:03f}".format(k, v) for k, v in val_logs.items()], end=' ')

            val_metrics = logs.get('metrics_logs')
            if val_metrics:
                print("| Val metrics:", end=' ')
                print(*["{}={:03f}".format(k, v) for k, v in val_metrics.items()])

    def on_batch_begin(self, batch, logs=None):
        pass

    def on_batch_end(self, batch, logs=None):
        step = logs["step"]
        batch_logs = logs.get("batch_logs")

        if step == "validation":
            self.train_pbar.set_description(step)  # training or validating
        postfix = OrderedDict()
        if batch_logs:
            for name, value in batch_logs.items():
                postfix[name] = '{0:1.5f}'.format(value)

        self.train_pbar.set_postfix(postfix)
        self.train_pbar.update(1)

    def on_train_begin(self, logs=None):
        self.total_epochs = logs["total_epochs"]
        self.train_loader_len = len(logs["train_loader"])
        self.val_loader_len = len(logs["val_loader"]) if logs["val_loader"] else None


class ReduceLROnPlateau(TrainCallback):
    """Reduce learning rate when a metric has stopped improving.
        Models often benefit from reducing the learning rate by a factor
        of 2-10 once learning stagnates. This scheduler reads a metrics
        quantity and if no improvement is seen for a 'patience' number
        of epochs, the learning rate is reduced.

        Args:
            optimizer (Optimizer): Wrapped optimizer.
            loss_step (str): Either "train" or "valid" to reduce the lr according
                to the train loss of valid loss
            mode (str): One of `min`, `max`. In `min` mode, lr will
                be reduced when the quantity monitored has stopped
                decreasing; in `max` mode it will be reduced when the
                quantity monitored has stopped increasing. Default: 'min'.
            factor (float): Factor by which the learning rate will be
                reduced. new_lr = lr * factor. Default: 0.1.
            patience (int): Number of epochs with no improvement after
                which learning rate will be reduced. Default: 10.
            verbose (bool): If True, prints a message to stdout for
                each update. Default: False.
            threshold (float): Threshold for measuring the new optimum,
                to only focus on significant changes. Default: 1e-4.
            threshold_mode (str): One of `rel`, `abs`. In `rel` mode,
                dynamic_threshold = best * ( 1 + threshold ) in 'max'
                mode or best * ( 1 - threshold ) in `min` mode.
                In `abs` mode, dynamic_threshold = best + threshold in
                `max` mode or best - threshold in `min` mode. Default: 'rel'.
            cooldown (int): Number of epochs to wait before resuming
                normal operation after lr has been reduced. Default: 0.
            min_lr (float or list): A scalar or a list of scalars. A
                lower bound on the learning rate of all param groups
                or each group respectively. Default: 0.
            eps (float): Minimal decay applied to lr. If the difference
                between new and old lr is smaller than eps, the update is
                ignored. Default: 1e-8.
    """

    def __init__(self, optimizer, loss_step="train", mode='min', factor=0.1, patience=10, verbose=False, threshold=1e-4,
                 threshold_mode='rel', cooldown=0, min_lr=0, eps=1e-8):
        super().__init__()
        self.loss_step = loss_step
        self.lr_sch = lr_scheduler.ReduceLROnPlateau(optimizer, mode, factor, patience,
                                                     verbose, threshold, threshold_mode,
                                                     cooldown, min_lr, eps)

    def on_epoch_end(self, epoch, logs=None):
        step = logs["step"]
        if step == 'training':
            for k, v in logs.items():
                if self.loss_step == "valid":
                    if k == 'val_loss':
                        if not v:
                            raise ValueError("ReduceLROnPlateau: No validation loss has been found")
                        self.lr_sch.step(v, epoch)
                else:
                    if k == 'train_loss':
                        self.lr_sch.step(v, epoch)


class ModelSaverCallback(TrainCallback):
    def __init__(self, to_dir, epochs, every_n_epoch=1):
        """
            Saves the model every n epochs in to_dir
        Args:
            to_dir (str): The path where to save the model
            epochs (int): Total number of epochs on which you'll train your model(s)
            every_n_epoch (int): Save the model every n epochs
        """
        super().__init__()
        self.epochs = epochs
        self.every_n_epoch = every_n_epoch
        self.to_dir = to_dir

    @staticmethod
    def restore_model(models, from_dir):
        """
            Restore model(s) from the given dir.
            If models are multiples they will be automatically matched to
            their the right files with a match between: class name -> file name
        Args:
            models (list): A list of models (Pytorch modules)
            from_dir (str): The directory where the model is stored
        """
        i = 0
        for model in models:
            file = os.path.join(from_dir, model.__class__.__name__ + ".pth")
            if os.path.isfile(file):
                model.load_state_dict(torch.load(from_dir))
                i += 1

        assert i+1 == len(models), "Not all models were restored. Please check that your passed models and files match"
        print(f"\n--- Model(s) restored from {from_dir} ---", end='\n\n')

    def on_epoch_end(self, epoch, logs=None):
        step = logs["step"]
        if step == 'training':
            if epoch % self.every_n_epoch == 0 or epoch == self.epochs:
                for k, m in logs['models'].items():
                    torch.save(m.state_dict(), os.path.join(self.to_dir, k + ".pth"))
                print(f"\n--- Model(s) saved in {self.to_dir} ---", end='\n\n')


class CosineAnnealingCallback(TrainCallback):
    def __init__(self):
        # TODO https://youtu.be/EKzSiuqiHNg?t=1h18m9s
        super().__init__()


class CycleLenCallback(TrainCallback):
    def __init__(self):
        """
            Number of cycles before lr is reset to the initial value.
            E.g if cycle_len = 3, then the lr is varied between a maximum
            and minimum value over 3 epochs.
        """
        # TODO implement (learner.py in fast.ai)
        super().__init__()


class GradientClippingCallback(TrainCallback):
    def __init__(self):
        """
        Gradient clipping
        # TODO implement: https://github.com/fastai/fastai/blob/master/fastai/model.py#L46
        """
        super().__init__()


class TensorboardVisualizerCallback(TrainCallback):
    def __init__(self, path_to_files):
        """
            Callback intended to be executed at each epoch
            of the training which goal is to display the result
            of the last validation batch in Tensorboard
        Args:
            path_to_files (str): The path where to store the log files
        """
        # TODO finish https://github.com/EKami/carvana-challenge/blob/master/src/nn/train_callbacks.py#L13
        super().__init__()
        self.path_to_files = path_to_files

    def on_epoch_begin(self, epoch, logs=None):
        pass

    def on_epoch_end(self, epoch, logs=None):
        pass
