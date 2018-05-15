import numpy as np
import h5py
from time import time
import matplotlib.pyplot as pl
from sklearn.model_selection import train_test_split
from sklearn.model_selection import KFold


start_time = time()

# np.random.seed(3)

with h5py.File('train_128.h5', 'r') as H:
    data = np.copy(H['data'])

with h5py.File('train_label.h5', 'r') as H:
    label = np.copy(H['label'])

with h5py.File('test_128.h5', 'r') as H:
    test_data = np.copy(H['data'])

print('train_128.h5: ' + str(data.shape))
print('train_label.h5: ' + str(label.shape))
print('test_128.h5: ' + str(test_data.shape))
print("\n------------------\n")


class Activation(object):
    def __tanh(self, x):
        return np.tanh(x)

    def __tanh_deriv(self, a):
        # a = np.tanh(x)
        return 1.0 - a**2

    def __logistic(self, x):
        return 1.0 / (1.0 + np.exp(-x))

    def __logistic_derivative(self, a):
        # a = logistic(x)
        return a * (1 - a)

    # define relu activation and relu derivative
    def __relu(self, x):
        index = (x < 0)
        x[index] = 0
        return x

    def __relu_deriv(self, a):
        index1 = (a >= 0)
        index0 = np.logical_not(index1)
        a[index1] = 1
        a[index0] = 0
        return a

    # default activation is relu
    def __init__(self, activation='relu'):
        if activation == 'logistic':
            self.f = self.__logistic
            self.f_deriv = self.__logistic_derivative
        elif activation == 'tanh':
            self.f = self.__tanh
            self.f_deriv = self.__tanh_deriv

        # choose relu
        elif activation == 'relu':
            self.f = self.__relu
            self.f_deriv = self.__relu_deriv


class HiddenLayer(object):
    def __init__(self, n_in, n_out, W=None, b=None,
                 activation='relu', weight_norm=False, dropout=False, keep_prob=0.5, weight_decay=False, weight_lambda=0.01):

        self.input = None
        self.activation = Activation(activation).f
        self.activation_deriv = Activation(activation).f_deriv
        # end-snippet-1

        # cause we use relu activation
        # so use He initialization
        self.W = np.random.randn(n_in, n_out) * np.sqrt(2.0 / n_in)
        self.b = np.zeros(n_out,)
        self.n_in = n_in
        self.n_out = n_out

        # set whether implement weight normalization
        self.weight_norm = weight_norm

        # set whether implement weight decay
        self.weight_decay = weight_decay
        self.weight_lambda = weight_lambda

        # set whether implement dropout
        self.dropout = dropout
        if dropout is True:
            print("Using dropout")
        self.keep_prob = keep_prob

        self.grad_W = np.zeros(self.W.shape)
        self.grad_b = np.zeros(self.b.shape)

        # batch normalization init gamma and beta
        self.gamma_BN = np.ones((1, n_in))
        self.beta_BN = 0  # np.zeros(n_in,)

        self.grad_gamma_BN = np.ones(self.gamma_BN.shape)
        self.grad_beta_BN = 0  # np.zeros(self.beta_BN.shape)

        self.BN_mean_total = []
        self.BN_var_total = []

        # momentum init v and b params
        self.v_w = np.zeros(self.W.shape)
        self.v_b = np.zeros(self.b.shape)
        # momentum with batch normalization init
        self.v_gamma_BN = np.zeros(self.gamma_BN.shape)
        self.v_beta_BN = 0

    def forward(self, input, BN=False, err_BN=1e-8):

        # judge the weight norm and implement
        if self.weight_norm is True:
            self.W = self.W / \
                (((self.W ** 2).sum(axis=0, keepdims=True)) ** 0.5)
            self.W = np.nan_to_num(self.W)

        # judge the dropout and implement
        if self.dropout is True:
            # set random probability matrix in every double layer
            prob = np.random.rand(1, input.shape[1])
            prob = prob < self.keep_prob
            input = input * prob

        if self.weight_decay is True:
            self.W = self.W + \
                self.weight_lambda * np.sum(self.W ** 2, axis=0) / 2

        if BN is True:
            input_mean = input.mean(axis=0, keepdims=True)
            input_var = input.var(axis=0, keepdims=True)
            input = (input - input_mean) / np.sqrt(input_var + err_BN)
            input = input * self.gamma_BN + self.beta_BN
            # input = np.dot(input, self.gamma_BN) + self.beta_BN
            self.BN_mean_total.append(input_mean)
            self.BN_var_total.append(input_var)

        lin_output = np.dot(input, self.W) + self.b
        self.output = (
            lin_output if self.activation is None
            else self.activation(lin_output)
        )
        self.input = input
        return self.output

    def forward_predict(self, input, BN=False, err_BN=1e-8):
        # judge the weight norm and implement
        # if self.weight_norm is True:
        #     self.W = self.W / (((self.W ** 2).sum(axis = 0, keepdims = True)) ** 0.5)
        #     self.W = np.nan_to_num(self.W)

        if BN is True:
            input_mean = np.mean(self.BN_mean_total)
            input_var = np.mean(self.BN_var_total)
            input = (input - input_mean) / np.sqrt(input_var + err_BN)
            input = input * self.gamma_BN + self.beta_BN
            # input = np.dot(input, self.gamma_BN) + self.beta_BN

        lin_output = np.dot(input, self.W) + self.b
        self.output = (
            lin_output if self.activation is None
            else self.activation(lin_output)
        )
        self.input = input
        return self.output

    # input is from previous layer, it is a_pre
    # delta is dz, delta_ is next layer's delta
    def backward(self, delta):
        self.grad_W = np.atleast_2d(self.input).T.dot(np.atleast_2d(delta))
        self.grad_b = np.sum(delta)
        # return delta_ for next layer
        delta_ = delta.dot(self.W.T) * self.activation_deriv(self.input)
        return delta_

    # backward with batch normalization calculate grad_gamma and grad_beta
    # gamma = ∆J/∆y * X ; beta = ∆J/∆y ; ∆J/∆y = y - y_hat because  f_derivative=1
    # formula from: https://chrisyeh96.github.io/2017/08/28/deriving-batchnorm-backprop.html
    # https://arxiv.org/pdf/1502.03167.pdf
    def backward_BN(self, delta):
        self.grad_W = np.atleast_2d(self.input).T.dot(np.atleast_2d(delta))
        ### Change #####
        self.grad_b = np.sum(delta)
        # return delta_ for next layer
        delta_ = delta.dot(self.W.T) * self.activation_deriv(self.input)
        # self.grad_gamma_BN = np.sum(np.atleast_2d(self.input).T.dot(np.atleast_2d(delta_)), axis=1, keepdims=True).T
        # self.grad_gamma_BN = np.sum(self.input * delta_, axis=0, keepdims=True)
        self.grad_gamma_BN = np.mean(
            delta_, axis=0, keepdims=True) * self.gamma_BN
        self.grad_beta_BN = np.mean(delta_)

        delta__ = delta_ * self.gamma_BN  # * self.activation_deriv(self.input)
        # delta__ = np.nan_to_num(delta__)

        return delta__


class InputOuput_Layer(object):
    def __init__(self, n_in, n_out, W=None, b=None, activation='relu', weight_norm=None):
        self.input = None
        self.activation = Activation(activation).f
        self.activation_deriv = Activation(activation).f_deriv

        # cause we use relu activation
        # so use He initialization
        self.W = np.random.randn(n_in, n_out) * np.sqrt(2.0 / n_in)
        self.b = np.zeros(n_out,)
        self.n_in = n_in
        self.n_out = n_out

        # set whether implement weight normalization
        self.weight_norm = weight_norm

        self.grad_W = np.zeros(self.W.shape)
        self.grad_b = np.zeros(self.b.shape)

        # batch normalization init gamma and beta
        self.gamma_BN = np.ones((1, n_in))
        self.beta_BN = 0  # np.zeros(n_in,)

        self.grad_gamma_BN = np.ones(self.gamma_BN.shape)
        self.grad_beta_BN = 0  # np.zeros(self.beta_BN.shape)

        # momentum init v and b params
        self.v_w = np.zeros(self.W.shape)
        self.v_b = np.zeros(self.b.shape)

        # momentum with batch normalization init
        self.v_gamma_BN = np.zeros(self.gamma_BN.shape)
        self.v_beta_BN = 0

    def forward(self, input, BN=False, err_BN=0):

        if self.weight_norm is True:
            self.W = self.W / \
                (((self.W ** 2).sum(axis=0, keepdims=True)) ** 0.5)
            self.W = np.nan_to_num(self.W)

        lin_output = np.dot(input, self.W) + self.b
        self.output = (
            lin_output if self.activation is None
            else self.activation(lin_output)
        )
        self.input = input
        return self.output

    def forward_predict(self, input, BN=False, err_BN=1e-8):

        lin_output = np.dot(input, self.W) + self.b
        self.output = (
            lin_output if self.activation is None
            else self.activation(lin_output)
        )
        self.input = input
        return self.output

    def backward(self, delta):
        self.grad_W = np.atleast_2d(self.input).T.dot(np.atleast_2d(delta))
        self.grad_b = np.sum(delta)
        # return delta_ for next layer
        delta_ = delta.dot(self.W.T) * self.activation_deriv(self.input)
        return delta_

    def backward_BN(self, delta):
        self.grad_W = np.atleast_2d(self.input).T.dot(np.atleast_2d(delta))
        self.grad_b = np.sum(delta)
        # return delta_ for next layer
        delta_ = delta.dot(self.W.T) * self.activation_deriv(self.input)

        return delta_


class MLP(object):

    def __init__(self, input_layers, hidden_layers, output_layers, activation='relu', weight_norm=False, dropout=False,
                 keep_prob=0.5, output_softmax_crossEntropyLoss=False, weight_decay=False, weight_lambda=0.01):
        # initialize layers
        self.layers = []
        self.params = []

        self.activation = activation
        self.weight_norm = weight_norm

        self.weight_decay = weight_decay
        self.weight_lambda = weight_lambda

        if self.weight_norm is True:
            print("Using weight normalization")

        # init layers
        self.layers.append(InputOuput_Layer(
            input_layers, hidden_layers[0], activation=activation, weight_norm=weight_norm
        ))
        if len(hidden_layers) >= 2:
            for i in range(len(hidden_layers) - 1):
                self.layers.append(HiddenLayer(
                    hidden_layers[i], hidden_layers[i +
                                                    1], activation=activation, weight_norm=weight_norm,
                    dropout=dropout, keep_prob=keep_prob, weight_decay=self.weight_decay, weight_lambda=self.weight_lambda
                ))
        self.layers.append(InputOuput_Layer(
            hidden_layers[-1], output_layers, activation=activation, weight_norm=weight_norm
        ))

        self.output_softmax_crossEntropyLoss = output_softmax_crossEntropyLoss
        if self.output_softmax_crossEntropyLoss is True:
            print("Using softmax and cross entropy loss in output")

    def forward(self, input, BN, err_BN):
        for layer in self.layers:
            output = layer.forward(input, BN, err_BN)
            input = output
        return output

    def forward_predict(self, input, BN=False, err_BN=1e-8):
        for layer in self.layers:
            output = layer.forward_predict(input, BN, err_BN)
            input = output
        return output

    def criterion_MSE(self, y, y_hat):
        if self.output_softmax_crossEntropyLoss is False:
            activation_deriv = Activation(self.activation).f_deriv
            # MSE
            error = y - y_hat
            loss = error**2
            # write down the delta in the last layer
            delta = -error * activation_deriv(y_hat) / 512
            # return loss and delta
            loss = np.sum(loss)

        # normal softmax
        elif self.output_softmax_crossEntropyLoss is True:
            activation_deriv = Activation(self.activation).f_deriv
            exps = np.exp(y_hat - np.max(y_hat, axis=1, keepdims=True))
            # print(np.max(y_hat, axis=0))
            last_y_out = exps / np.sum(exps, axis=1, keepdims=True)
            error = (last_y_out - y)
            loss = - \
                np.sum(y * np.log(last_y_out), axis=1, keepdims=True)
            # write down the delta in the last layer
            delta = error * activation_deriv(y_hat) / 512
        return loss, delta

 # define softmax and cross-entropy loss
 # y_hat is last hidden layer output, y is real value
    def criterion_SCE(self, y, y_hat):
        #activation_deriv = Activation(self.activation).f_deriv
        exps = np.exp(y_hat - np.max(y_hat))
        last_y_out = exps / np.sum(exps)
        error = last_y_out - y
        loss = np.sum(np.multiply(y, np.log(last_y_out)))
        # write down the delta in the last layer
        delta = error  # dL/dz
        # return loss and delta
        return loss, delta

    def backward(self, delta):
        for layer in reversed(self.layers):
            delta = layer.backward(delta)

    def backward_BN(self, delta):
        for layer in reversed(self.layers):
            delta = layer.backward_BN(delta)

    def update(self, lr, momentum, gamma_MT):
        # Update without momentum
        if momentum is False:
            for layer in self.layers:
                layer.W -= lr * layer.grad_W
                layer.b -= lr * layer.grad_b
        # Update with momentum
        elif momentum is True:
            for i, layer in enumerate(self.layers):
                layer.v_w = gamma_MT * layer.v_w + lr * layer.grad_W
                layer.W -= layer.v_w
                layer.v_b = gamma_MT * layer.v_b + lr * layer.grad_b
                layer.b -= layer.v_b

    def update_BN(self, lr, momentum, gamma_MT):
        # Update without momentum
        if momentum is False:
            for layer in self.layers:
                layer.W -= lr * layer.grad_W
                layer.b -= lr * layer.grad_b
                layer.gamma_BN -= lr * layer.grad_gamma_BN
                layer.beta_BN -= lr * layer.grad_beta_BN

        # Update with momentum
        elif momentum is True:
            # initial v params
            for i, layer in enumerate(self.layers):
                layer.v_w = gamma_MT * layer.v_w + lr * layer.grad_W
                layer.W -= layer.v_w
                layer.v_b = gamma_MT * layer.v_b + lr * layer.grad_b
                layer.b -= layer.v_b
                layer.v_gamma_BN = gamma_MT * layer.v_gamma_BN + lr * layer.grad_gamma_BN
                layer.gamma_BN -= layer.v_gamma_BN
                layer.v_beta_BN = gamma_MT * layer.v_beta_BN + lr * layer.grad_beta_BN
                layer.beta_BN -= layer.v_beta_BN

    # mini batch training
    def mini_batches_random(self, X, y, mini_batch_size):
        # np.random.seed(seed)
        # the feature at columns
        num_samples = X.shape[0]
        mini_batches = []

        permutation = list(np.random.permutation(num_samples))
        rand_X = X[permutation, :]
        rand_y = y[permutation, :]  # .reshape(num_samples, 10)

        num_complete = num_samples // mini_batch_size

        for i in range(num_complete):
            mini_batch_X = rand_X[i *
                                  mini_batch_size: (i + 1) * mini_batch_size, :]
            mini_batch_y = rand_y[i *
                                  mini_batch_size: (i + 1) * mini_batch_size, :]

            mini_batch = (mini_batch_X, mini_batch_y)
            mini_batches.append(mini_batch)

        if num_samples % mini_batch_size != 0:
            mini_batch_X = rand_X[num_complete * mini_batch_size:, :]
            mini_batch_y = rand_y[num_complete * mini_batch_size:, :]

            mini_batch = (mini_batch_X, mini_batch_y)
            mini_batches.append(mini_batch)
        return mini_batches

    def fit(self, X, y, learning_rate=0.1, epochs=100,
            gd='mini_batch', momentum=False, gamma_MT=0.9, mini_batch_size=64, batch_norm=False, err_BN=1e-8):
        X = np.array(X)
        y = np.array(y)
        to_return = np.zeros(epochs)
        self.BN = batch_norm
        if self.BN is True:
            print("Using batch normalization")
        self.err_BN = err_BN
        if momentum is True:
            print('Using momentum')

        # Implement Gradient Descent
        if gd == 'GD':
            print("Using GD")
            for k in range(epochs):
                epoch_start_time = time()
                loss = np.zeros(X.shape[0])
                for it in range(X.shape[0]):
                    i = np.random.randint(X.shape[0])
                    # forward pass
                    y_hat = self.forward(X[i], batch_norm, err_BN)
                    # backward pass
                    loss[it], delta = self.criterion_MSE(y[i], y_hat)
                    self.backward(delta)
                    # update
                    self.update(learning_rate, momentum, gamma_MT)
                to_return[k] = np.mean(loss)
                print("the epoch %s loss is" % str(k + 1))
                print(to_return[k])
                epoch_end_time = time()
                print("\n--- this epoch used:\n--- %2f seconds" %
                      (epoch_end_time - epoch_start_time))
                print("-------------------------")

        # Implement Stochastic Gradient Descent
        if gd == 'SGD':
            print("Using SGD")
            for k in range(epochs):
                epoch_start_time = time()
                loss = 0
                i = np.random.randint(X.shape[0])
                # forward pass
                y_hat = self.forward(X[i], batch_norm, err_BN)
                # backward pass
                loss, delta = self.criterion_MSE(y[i], y_hat)
                self.backward(delta)
                # update
                self.update(learning_rate, momentum, gamma_MT)
                to_return[k] = np.mean(loss)
                print("the epoch %s loss is" % str(k + 1))
                print(to_return[k])
                epoch_end_time = time()
                print("\n--- this epoch used:\n--- %2f seconds" %
                      (epoch_end_time - epoch_start_time))
                print("-------------------------")

        # Implement Mini Batch
        if gd == 'mini_batch':
            print("Using mini batch")
            print("the mini batch size is {}".format(mini_batch_size))
            for k in range(epochs):
                epoch_start_time = time()
                loss = np.zeros(X.shape[0])
                # seed = k
                mini_batches = self.mini_batches_random(X, y, mini_batch_size)

                for it, mini_batch in enumerate(mini_batches):
                    loss_it = 0
                    (mini_batch_X, mini_batch_y) = mini_batch
                    # forward pass
                    y_hat = self.forward(mini_batch_X, batch_norm, err_BN)
                    # backward pass
                    loss_it, delta = self.criterion_MSE(mini_batch_y, y_hat)
                    loss[it] = np.mean(loss_it)

                    # judge BN
                    if batch_norm is False:
                        self.backward(delta)
                        # update
                        self.update(learning_rate, momentum, gamma_MT)
                    elif batch_norm is True:
                        self.backward_BN(delta)
                        # update
                        self.update_BN(learning_rate, momentum, gamma_MT)

                to_return[k] = np.mean(loss)
                print("the epoch %s loss is" % str(k + 1))
                print(to_return[k])
                epoch_end_time = time()
                print("\n--- this epoch used:\n--- %2f seconds" %
                      (epoch_end_time - epoch_start_time))
                print("-------------------------")

        return to_return

    def predict(self, x, model):
        x = np.array(x)
        output = model.forward_predict(x, self.BN, self.err_BN)
        if self.output_softmax_crossEntropyLoss is True:
            exps_out = np.exp(output)
            output = exps_out / np.sum(exps_out, axis=1, keepdims=True)
        return output


# Try different MLP models
nn = MLP(128, [100, 80, 50, 40, 30, 20], 10, 'tanh', weight_norm=False, dropout=False, keep_prob=0.8,
         output_softmax_crossEntropyLoss=False, weight_decay=False, weight_lambda=0.0004)


def splitdata():
    input_data = np.array(data, dtype=float)
    output_data = np.array(label, dtype=float)
    # Normalization Data (x-mu)/delta
    input_data = (input_data - input_data.mean(axis=0, keepdims=True)
                  ) / input_data.std(axis=0, keepdims=True)
    onehot_label = np.array(np.eye(10)[label.reshape(-1)], dtype=float)

    data_index = int(input_data.shape[0]*0.8)
    indices = np.random.permutation(input_data.shape[0])
    train_index = indices[:data_index]
    test_index = indices[data_index:]


    rand_tran_data, rand_tran_label = input_data[train_index], onehot_label[train_index]
    rand_test_data, rand_test_label = input_data[test_index], onehot_label[test_index]

       # rand_tran_label = np.array(
    #     np.eye(10)[rand_tran_label.reshape(-1)], dtype=float)
    # rand_test_label = np.array(
    #     np.eye(10)[rand_test_label], dtype=float)
    return rand_tran_data, rand_tran_label, rand_test_data, rand_test_label



rand_tran_data, rand_tran_label, rand_test_data, rand_test_label = splitdata()


MSE = nn.fit(rand_tran_data, rand_tran_label, learning_rate=0.1,
             epochs=20, gd='mini_batch', momentum=False, gamma_MT=0.8, mini_batch_size=512, batch_norm=False)

print("\n------------------\n")
print('loss:%f' % MSE[-1])

# pl.figure(figsize=(15,4))
# pl.plot(MSE)
# pl.grid()

# calculate time
end_fit_time = time()
print("\n--- Fit used:\n--- %2f seconds" % (end_fit_time - start_time))

# calculate accuracy
output = nn.predict(rand_test_data, nn)
output_array = np.array(output)
output_01 = (output_array == output_array.max(
    axis=1, keepdims=1)).astype(float)

acc_num = 0
for i in range(len(output_01)):
    if False not in (output_01[i] == rand_test_label[i]):
        acc_num += 1

acc = acc_num / len(rand_test_label)

print("\n--- the accuracy is:\n--- {:.4%}".format(float(acc)))

# calculate time
end_total_time = time()
print("\n--- Predict used:\n--- %2f seconds" % (end_total_time - end_fit_time))
print("\n--- Total used:\n--- %2f seconds" % (end_total_time - start_time))


print("\n\n-------------------------\n--------------------------")


pl.figure(figsize=(15, 4))
pl.plot(MSE)
pl.grid()


