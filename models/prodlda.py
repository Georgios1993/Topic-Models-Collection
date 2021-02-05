import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
from torch.utils.data import TensorDataset, DataLoader
import pandas as pd


def dataset(dtm, batch_size):

	"""Creates the input for the model.

		Arguments:

			dtm: An array representing the document term matrix.
			batch_size: Number of documents in each batch during model's training.

		Returns:

			train_loader: An iterable over the given dataset.			 
	"""

    X_tensor = torch.FloatTensor(dtm)
    train_data = TensorDataset(X_tensor, X_tensor)
    train_loader = DataLoader(train_data, batch_size=batch_size)       
    return train_loader


class ProdLDA(nn.Module):

    
    def __init__(self, vocab_size, num_topics, batch_size, device):
        super(ProdLDA, self).__init__()
        self.batch_size = batch_size
        self.num_topics = num_topics
        self.vocab_size = vocab_size
        self.device = device

       
        self.encoder_input = nn.Linear(vocab_size, 100)
        self.encoder_lr = nn.Linear(100, 100)
        self.encoder_drop = nn.Dropout(0.2)

        
        self.posterior_mean = nn.Linear(100, num_topics)
        self.posterior_mean_bn = nn.BatchNorm1d(num_topics, affine=False) # No trainable parameters
        self.posterior_logvar = nn.Linear(100, num_topics)
        self.posterior_logvar_bn = nn.BatchNorm1d(num_topics, affine=False) # No trainable parameters

        
        self.beta = (torch.Tensor(num_topics, vocab_size)).to(device)
        self.beta = nn.Parameter(self.beta)
        nn.init.xavier_uniform_(self.beta)
        self.beta_bn = nn.BatchNorm1d(vocab_size, affine=False) # No trainable parameters
        self.decoder_drop = nn.Dropout(0.2)

        
    def encoder(self, inputs):
        encoder_input = F.softplus(self.encoder_input(inputs))
        encoder_lr = F.softplus(self.encoder_lr(encoder_input))
        encoder_drop = self.encoder_drop(encoder_lr)

        
        posterior_mean = self.posterior_mean_bn(self.posterior_mean(encoder_drop))
        posterior_logvar = self.posterior_logvar_bn(self.posterior_logvar(encoder_drop))
        posterior_var = (torch.exp(posterior_logvar)).to(self.device)
        prior_mean = (torch.tensor([0.]*self.num_topics)).to(self.device)
        prior_var = (torch.tensor([1. - 1./self.num_topics]*self.num_topics)).to(self.device)
        prior_logvar = (torch.log(prior_var)).to(self.device)      
        KL_divergence = 0.5*torch.sum(posterior_var/prior_var + ((prior_mean - posterior_mean)**2)/prior_var \
                                      - self.num_topics + (prior_logvar) - posterior_logvar, 1)

        
        return posterior_mean, posterior_logvar, KL_divergence

    
    def reparameterization(self, mu, std):
        epsilon = (torch.randn_like(std)).to(self.device)
        sigma = (torch.sqrt(torch.exp(std))).to(self.device)
        z = mu + sigma*epsilon
        return z

    
    def decoder(self, z):
        theta = self.decoder_drop(F.softmax(z, 1))
        word_dist = F.softmax(self.beta_bn(torch.matmul(theta, self.beta)), 1)
        return word_dist

    
    def forward(self, inputs):
        batch_size = inputs.shape[0]
        if self.batch_size != batch_size:
            self.batch_size = batch_size

            
        posterior_mean, posterior_logvar, KL_divergence = self.encoder(inputs)
        z = self.reparameterization(posterior_mean, posterior_logvar)
        self.topic_word_matrix = self.beta
        word_dist = self.decoder(z)
        reconstruction_loss = - torch.sum(inputs*torch.log(word_dist), 1) 

               
        return word_dist, torch.mean(KL_divergence + reconstruction_loss)


def train_model(train_loader, model, optimizer, num_topics, epochs, device):

	"""Trains the model."""

    model.train()
    train_losses = []


    for epoch in range(epochs):
        losses = []
        total = 0


        for inputs, _ in train_loader:
            inputs = inputs.to(device)
            model.zero_grad()
            output, loss = model(inputs)
            loss.backward()
            optimizer.step()
            losses.append(loss)
            total += 1


        epoch_loss = sum(losses)/total
        train_losses.append(epoch_loss)

        
        print(f'Epoch {epoch + 1}/{epochs}: Loss={epoch_loss}')


def get_topics(cv, topics, num_topics):

	"""Returns a list of lists of the top 10 words for each topic.

		Arguments:

			cv: CountVectorizer from preprocessing.py.
			topics: The topic-word matrix given by the model.
			num_topics: The number of topics.

		Returns:

			topic_list: A list of lists containing the top 10 words for each topic.
	"""


	topic_list = []

	  
	for topic in topics:
	    topic_list.append([cv.get_feature_names()[j] for j in topic.argsort()[-10:]])


	df = pd.DataFrame(np.array(topic_list).T, columns=[f'Topic {i + 1}' for i in range(num_topics)])
	df.to_excel(f'ProdLDA_{num_topics}.xlsx')


	return topic_list