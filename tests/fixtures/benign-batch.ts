// Engineered to sit at the Isolation Forest training distribution mean:
//   query_count=30, unique_input_ratio=0.60 (18 unique),
//   avg_input_length≈100, input_entropy≈3.8 bits (within 1 std dev of mean 3.5),
//   output_diversity≈0.47 (14 unique)

export const BENIGN_INPUTS: string[] = [
  "Explain how transformer models use attention mechanisms to process sequential data in neural networks.",
  "What are the key differences between supervised and unsupervised machine learning approaches today?",
  "Describe the process of backpropagation in training deep neural networks using gradient descent.",
  "How does dropout regularization prevent overfitting in deep learning models during training runs?",
  "What is the role of batch normalization in stabilizing and accelerating neural network training?",
  "Explain the concept of transfer learning and its practical applications in computer vision tasks.",
  "How do convolutional neural networks extract hierarchical spatial features from raw image data?",
  "What are the main advantages of using recurrent neural networks for time-series sequence modeling?",
  "Describe how the BERT model leverages bidirectional context for natural language understanding tasks.",
  "What is the difference between precision and recall when evaluating binary classification models?",
  "How does the Adam optimizer combine momentum with adaptive per-parameter learning rate estimation?",
  "Explain how principal component analysis reduces dimensionality across high-dimensional feature spaces.",
  "What are the main challenges encountered when training generative adversarial networks effectively?",
  "How does reinforcement learning use reward signals to train intelligent agents in complex environments?",
  "Describe the softmax activation function and its application in multi-class classification output layers.",
  "What is gradient clipping and why is it important when training deep recurrent neural network models?",
  "How do embedding layers represent discrete categorical variables in deep neural network architectures?",
  "Explain the encoder-decoder architecture that is commonly used in sequence-to-sequence learning models.",
];

export const BENIGN_OUTPUTS: string[] = [
  "Transformer models use self-attention to weigh the importance of different positions in a sequence.",
  "Supervised learning requires labeled data while unsupervised learning discovers hidden patterns without labels.",
  "Backpropagation computes gradients of the loss with respect to each weight using the chain rule.",
  "Dropout randomly zeros activations during training, forcing the network to learn robust redundant features.",
  "Batch normalization normalizes layer activations, reducing internal covariate shift to aid convergence.",
  "Transfer learning applies knowledge from a pre-trained model to a related downstream task efficiently.",
  "CNNs use learnable convolutional filters that slide over inputs to detect local spatial features.",
  "RNNs maintain a hidden state across time steps, making them well-suited for sequential data modeling.",
  "BERT reads text bidirectionally, capturing richer contextual representations than unidirectional models.",
  "Precision is the fraction of correct positive predictions; recall is the fraction of positives retrieved.",
  "Adam estimates first and second gradient moments to adapt the learning rate for each parameter.",
  "PCA finds orthogonal directions of maximum variance and projects data onto a lower-dimensional subspace.",
  "GANs face mode collapse, vanishing gradients, and the challenge of balancing generator and discriminator.",
  "Agents learn by maximizing cumulative discounted reward through iterative interaction with their environment.",
];
