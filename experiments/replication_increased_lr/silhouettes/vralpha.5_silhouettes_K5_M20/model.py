# Define the model
class silhouettes_model(nn.Module):
    def __init__(self):
        super(silhouettes_model, self).__init__()

        self.fc1 = nn.Linear(784, 500)
        self.fc21 = nn.Linear(500, 200)
        self.fc22 = nn.Linear(500, 200)

        self.fc3 = nn.Linear(200, 500)
        self.fc4 = nn.Linear(500, 784)

        self.K = K

    def encode(self, x):
        # h1 = F.relu(self.fc1(x))
        h1 = torch.tanh(self.fc1(x))

        return self.fc21(h1), self.fc22(h1)

    def reparameterize(self, mu, logstd, test=False):
        std = torch.exp(logstd)
        if test == True:
            eps = torch.zeros_like(mu)
        else:
            eps = torch.randn_like(std)
        return mu + eps * std

    def decode(self, z, test=False):
        h3 = torch.tanh(self.fc3(z))

        return torch.sigmoid(self.fc4(h3))

    def forward(self, x):
        mu, logstd = self.encode(x.view(-1, 784))
        z = self.reparameterize(mu, logstd)
        return self.decode(z), mu, logstd

    def compute_loss_for_batch(self, data, model, K=K, test=False, alpha=alpha):
        # data = (N,560)
        if model_type == "vae":
            alpha = 1
        elif model_type in ("iwae", "vrmax"):
            alpha = 0
        elif model_type == "general_alpha" or model_type == "vralpha":
            # use whatever alpha is defined in hyperparameters
            if abs(alpha - 1) <= 1e-3:
                print(
                    "Can't plug 1 into general alpha formula, use model_type='vae' instead"
                )
                raise Exception

        data_k_vec = data.repeat_interleave(K, 0)

        mu, logstd = model.encode(data_k_vec)
        # (B*K, #latents)
        z = model.reparameterize(mu, logstd)

        # summing over latents due to independence assumption
        # (B*K)
        log_q = compute_log_probabitility_gaussian(z, mu, logstd)

        log_p_z = torch.sum(-0.5 * z**2, 1) - 0.5 * z.shape[1] * T.log(
            torch.tensor(2 * np.pi)
        )
        decoded = model.decode(z)  # decoded = (pmu, plog_sigma)
        log_p = compute_log_probabitility_bernoulli(decoded, data_k_vec)
        # hopefully this reshape operation magically works like always
        if model_type == "iwae" or test == True:
            log_w_matrix = (log_p_z + log_p - log_q).view(-1, K)
        elif model_type == "vae":
            # treat each sample for a given data point as you would treat all samples in the minibatch
            # 1/K value because loss values seemed off otherwise
            log_w_matrix = (log_p_z + log_p - log_q).view(-1, 1) * 1 / K
        elif model_type == "general_alpha" or model_type == "vralpha":
            log_w_matrix = (log_p_z + log_p - log_q).view(-1, K) * (1 - alpha)
        elif model_type == "vrmax":
            log_w_matrix = (
                (log_p_z + log_p - log_q).view(-1, K).max(axis=1, keepdim=True).values
            )

        log_w_minus_max = log_w_matrix - torch.max(log_w_matrix, 1, keepdim=True)[0]
        ws_matrix = torch.exp(log_w_minus_max)
        ws_norm = ws_matrix / torch.sum(ws_matrix, 1, keepdim=True)

        if model_type == "vralpha" and not test:
            sample_dist = Multinomial(1, ws_norm)
            ws_sum_per_datapoint = log_w_matrix.gather(
                1, sample_dist.sample().argmax(1, keepdim=True)
            )
        else:
            ws_sum_per_datapoint = torch.sum(log_w_matrix * ws_norm, 1)

        if model_type in ["general_alpha", "vralpha"] and not test:
            ws_sum_per_datapoint /= 1 - alpha

        loss = -torch.sum(ws_sum_per_datapoint)

        return decoded, loss
